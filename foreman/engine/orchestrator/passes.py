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
from ...domain.errors import EngineCommandInterrupt, TaskStoppedInterrupt
from ...domain.holds import Hold, cuts_running_step, task_hold
from ...domain.models import (
    Project,
    Task,
)
from ...runner import process
from ...runner.process import EngineShutdown
from ..errors import (
    LeaseLostError,
    OrchestratorError,
    QuotaPauseError,
    TaskExecutionError,
)
from ..holds import hold_of, sprint_block_over
from ..limits import (
    resolve_project_settings,
)
from ..results import (
    ProjectRunResult,
    quota_run_result,
)
from .base import OrchestratorBase

#: How long the agent's process group is given to die after a user's Stop.
STOP_TERMINATE_GRACE_SECONDS = 2.0


def describe_hold(hold: Hold) -> str:
    """One line on a hold, for a run result or a rejected request."""

    if hold.kind == "block":
        return f"the {hold.scope} is blocked ({hold.reason})"
    if hold.kind == "blocking":
        return f"it is being blocked ({hold.reason})"
    return f"paused by {hold.by}" if hold.by else "paused"


class ProjectPass(OrchestratorBase):
    """Running a project pass."""

    def _poll_commands(self, task_id: str) -> None:
        """Give a user's Stop, and the resident engine, a chance to interrupt this task.

        A user who stopped the task (a pause with mode ``now``, ADR-0043)
        gets the running step cut: the agent's process group is ended and
        ``TaskStoppedInterrupt`` settles the run as killed on the way out.
        Otherwise the resident engine reads its commands and raises
        ``EngineCommandInterrupt`` when one needs the step stopped. Any
        *other* exception is deliberately not caught: a poll that cannot read
        the database is a broken control channel, and hiding it would leave a
        user's Stop silently ignored.
        """

        task = self.store.get_task(task_id)
        if task is not None and cuts_running_step(task):
            process.terminate_all(grace_seconds=STOP_TERMINATE_GRACE_SECONDS)
            raise TaskStoppedInterrupt(task_id, requested_by=task.paused_by)
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
            # A request to run a task does not pass a user's hold (ADR-0043).
            hold = hold_of(self.store, task)
            if hold is not None:
                return ProjectRunResult(
                    project_id=project.id,
                    executed_task_ids=(),
                    blocked_task_ids=(),
                    stop_reason="held",
                    detail=f"{task.task_key or task.id} is held: {describe_hold(hold)}",
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

        # A planned sprint waits for a user to start it, or for Foreman to
        # finish the sprint before it where the project lets Foreman finish
        # sprints; a block on either holds it (ADR-0043).
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
            if sprint is not None and sprint_block_over(self.store, sprint) is not None:
                # A blocked sprint, or workspace, holds what comes after it
                # too: it is not finished and the next one does not start.
                stop_reason = "held"
            elif sprint is not None and self.sprints.fully_resolved(sprint):
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
                elif any(
                    t.status in {"todo", "in_progress"} and task_hold(t) is not None
                    for t in remaining
                ):
                    stop_reason = "held"
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
            # A user's pause releases the queue (ADR-0043): the decision is
            # still recorded, and the task carries on when it is resumed.
            if blocked_kind(task, gates) == "gate" and task_hold(task) is None:
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
