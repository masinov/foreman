"""A project pass: the next task, approved merges, the commands read between tasks.
"""

from __future__ import annotations

import time

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
from .base import _LOGGER, OrchestratorBase

#: The steps a running step may carry out for another task: both are quick
#: and work in the integration tree.
MERGE_STEP_ROLES = frozenset({"_builtin:merge", "_builtin:mark_done"})


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

        if self._carrying_out_merges:
            # A merge being carried out for another task takes seconds; a
            # command is heard at the running step's next tick.
            return
        if self.command_poll is not None:
            self.command_poll(task_id)
        self._carry_out_approved_merges(task_id)

    def _carry_out_approved_merges(self, running_task_id: str) -> None:
        """Merge other tasks whose merge a person has approved, now.

        Called from the running step's command poll, so before each step and
        on every tick of an agent step. An approval made while the engine is
        busy leaves its task waiting at the merge step; without this it
        waited until the task in hand had finished or parked, which can be
        the length of a develop step. Only the merge and mark-done steps are
        run here: they are quick and work in the integration tree, not in
        the running task's. A merge that fails or conflicts leaves its task
        at the step the workflow sends it to, for the queue.
        """

        now = time.monotonic()
        last = self._last_approved_merge_check
        if last is not None and now - last < self.approved_merge_check_seconds:
            return
        self._last_approved_merge_check = now

        running = self.store.get_task(running_task_id)
        project = self.store.get_project(running.project_id) if running else None
        if project is None:
            return
        workflow = self.workflows.get(project.workflow_id)
        if workflow is None:
            return
        waiting = []
        for task in self.store.list_tasks(project_id=project.id, status="in_progress"):
            if task.id == running_task_id or not task.workflow_current_step:
                continue
            step = workflow.get_step(task.workflow_current_step)
            if step is not None and step.role == "_builtin:merge":
                waiting.append(task)
        if not waiting:
            return

        self._carrying_out_merges = True
        try:
            for task in waiting:
                if self.leases.acquire(task, project) is None:
                    continue
                try:
                    self.run_task(project, workflow, task, only_roles=MERGE_STEP_ROLES)
                except LeaseLostError:
                    continue
                except Exception as exc:  # noqa: BLE001 - one task's merge must not end another's step
                    _LOGGER.warning(
                        "Approved merge of task %s failed while another task was running: %s",
                        task.id,
                        exc,
                    )
                    self.block_task_for_error(task.id, str(exc))
        finally:
            self._carrying_out_merges = False

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
        while True:
            if (
                executed_task_ids
                and self.yield_between_tasks is not None
                and self.yield_between_tasks()
            ):
                stop_reason = "yielded"
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
        )

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
