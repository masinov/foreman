"""A project pass: the next task, one at a time, and the commands read between tasks.

The engine runs one task at a time (ADR-0039). A task waiting for a user's
decision at a gate holds the queue: no other task starts until it is
decided, and then it is carried on before anything else. So every task
starts from the default branch as the last one left it, and two tasks'
branches never overlap in time.
"""

from __future__ import annotations

from ...definitions.gate_steps import blocked_kind, workflow_gate_steps
from ...definitions.workflows import (
    WorkflowDefinition,
)
from ...domain.errors import EngineCommandInterrupt
from ...domain.models import (
    Project,
    Task,
)
from ...runner.process import EngineShutdown
from ..errors import (
    LeaseLostError,
    OrchestratorError,
    QuotaPauseError,
    TaskExecutionError,
)
from ..limits import (
    resolve_project_settings,
)
from ..results import (
    ProjectRunResult,
    quota_run_result,
)
from .base import OrchestratorBase

class ProjectPass(OrchestratorBase):
    """Running a project pass."""

    def _poll_commands(self, task_id: str) -> None:
        """Give the resident engine a chance to interrupt this task.

        Raises ``EngineCommandInterrupt`` when the engine wants the step
        stopped. Any *other* exception from the callback is deliberately not
        caught: a command poll that cannot read the database is a broken
        control channel, and hiding it would leave an operator's `pause`
        silently ignored.
        """

        if self.command_poll is not None:
            self.command_poll(task_id)

    def run_project(
        self,
        project_id: str,
        *,
        task_id: str | None = None,
        maintenance: bool = True,
    ) -> ProjectRunResult:
        """Run one project's active workflow until no runnable task remains.

        ``maintenance`` controls the once-per-startup housekeeping (retention
        pruning and crash recovery). A resident engine passes ``False`` on an
        idle wake: nothing has executed since the last pass, so re-pruning and
        re-scanning for orphans on every wake would be pure load.
        """

        project = self.store.get_project(project_id)
        if project is None:
            raise OrchestratorError(f"Unknown project {project_id!r}.")
        settings = resolve_project_settings(project)
        workflow = self._load_workflow_for_project(project)
        self.task_worktrees.preflight(project)
        if maintenance:
            self.retention.prune_old_history(project, settings=settings)
            self.recovery.recover_orphaned_tasks(project.id)

        executed_task_ids: list[str] = []
        blocked_task_ids: list[str] = []
        if task_id is not None:
            task = self.store.get_task(task_id)
            if task is None or task.project_id != project.id:
                raise OrchestratorError(
                    f"Task {task_id!r} does not belong to project {project.id!r}."
                )
            # Acquire the lease before running; skip if task is already leased
            # by another orchestrator.
            if self.leases.acquire(task, project) is None:
                raise OrchestratorError(
                    f"Task {task_id!r} is already leased by another orchestrator."
                )
            try:
                completed = self._run_task_isolated(project, workflow, task)
            except QuotaPauseError as exc:
                return quota_run_result(project, exc, executed_task_ids, blocked_task_ids)
            executed_task_ids.append(completed.id)
            if completed.status == "blocked":
                blocked_task_ids.append(completed.id)
            return ProjectRunResult(
                project_id=project.id,
                executed_task_ids=tuple(executed_task_ids),
                blocked_task_ids=tuple(blocked_task_ids),
                stop_reason="task_complete",
            )

        # A planned sprint waits for a person to activate it, or for Foreman
        # to finish the sprint before it; the engine never starts one on its
        # own (owner, 2026-11-21).
        stop_reason = "idle"
        detail = ""
        while True:
            if (
                executed_task_ids
                and self.yield_between_tasks is not None
                and self.yield_between_tasks()
            ):
                stop_reason = "yielded"
                break
            waiting = self._task_waiting_for_a_decision(project, workflow)
            if waiting is not None:
                # One task at a time (ADR-0039): nothing else starts until a
                # user decides. The decision is a database write, which wakes
                # a resident engine, and the decided task then comes first.
                stop_reason = "waiting_for_decision"
                detail = f"{waiting.task_key or waiting.id} waits for a decision."
                break
            task = self.selector.select_next_task(project)
            if task is not None:
                try:
                    completed = self._run_task_isolated(project, workflow, task)
                except QuotaPauseError as exc:
                    return quota_run_result(
                        project, exc, executed_task_ids, blocked_task_ids
                    )
                executed_task_ids.append(completed.id)
                if completed.status == "blocked":
                    blocked_task_ids.append(completed.id)
                continue

            # No runnable task — check sprint state.
            sprint = self.store.get_active_sprint(project.id)
            if sprint is not None and self.sprints.fully_resolved(sprint):
                result = self.sprints.resolve(project, sprint)
                if result is None:
                    # Autonomous mode: next sprint now active — keep looping.
                    continue
                stop_reason = result
            else:
                remaining = (
                    self.store.list_tasks(sprint_id=sprint.id)
                    if sprint is not None
                    else []
                )
                if any(t.status == "blocked" for t in remaining):
                    stop_reason = "blocked"
                elif any(t.status in {"todo", "in_progress"} for t in remaining):
                    stop_reason = "waiting"
                else:
                    stop_reason = "idle"
            break

        return ProjectRunResult(
            project_id=project.id,
            executed_task_ids=tuple(executed_task_ids),
            blocked_task_ids=tuple(blocked_task_ids),
            stop_reason=stop_reason,
            detail=detail,
        )

    def _task_waiting_for_a_decision(
        self, project: Project, workflow: WorkflowDefinition
    ) -> Task | None:
        """The active sprint's task stopped at a gate for a user's decision, if any.

        A task blocked by a failure does not hold the queue: it needs fixing,
        not a decision, and may wait for days.
        """

        sprint = self.store.get_active_sprint(project.id)
        if sprint is None:
            return None
        gates = workflow_gate_steps(workflow)
        for task in self.store.list_tasks(sprint_id=sprint.id, status="blocked"):
            if blocked_kind(task, gates) == "gate":
                return task
        return None

    def _run_task_isolated(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
    ) -> Task:
        """Run one task, tagging any failure with the task it belongs to.

        Shutdown and lease loss are engine-level events and pass through
        untouched. Everything else — ``OrchestratorError``, ``GitError``, an
        unexpected exception — is re-raised as :class:`TaskExecutionError` so
        the caller knows which task to block instead of guessing.
        """

        try:
            return self.run_task(project, workflow, task)
        except (
            EngineCommandInterrupt,
            EngineShutdown,
            KeyboardInterrupt,
            LeaseLostError,
            QuotaPauseError,
            TaskExecutionError,
        ):
            raise
        except Exception as exc:
            raise TaskExecutionError(task.id, exc) from exc
