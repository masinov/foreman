"""One task under a lease, and blocking, releasing or stopping one.
"""

from __future__ import annotations

from ...definitions.question import QUESTION_BLOCKED_REASON
from ...definitions.workflows import (
    WorkflowDefinition,
)
from ...domain.models import (
    Project,
    Task,
    utc_now_text,
)
from ...repo.context import (
    build_project_context,
)
from ..branch_sync import (
    context_mirror_dirs,
)
from ..errors import (
    OrchestratorError,
)
from .base import OrchestratorBase, generate_branch_name


class TaskRun(OrchestratorBase):
    """Running one task."""

    def block_task_for_error(
        self,
        task_id: str,
        reason: str,
        *,
        attention_trigger: str = "task_blocked",
    ) -> Task | None:
        """Block one task after an engine-level failure and raise attention.

        Used by the resident engine to isolate a failed task: the task is
        parked as ``blocked`` with the failure text, a system run records what
        happened, and ``engine.attention_needed`` reaches the supervision
        digest through the same path a workflow block takes. Returns the task,
        or None when it no longer exists.
        """

        task = self.store.get_task(task_id)
        if task is None:
            return None

        project = self.store.get_project(task.project_id)
        if project is not None:
            self.leases.release(task, project)

        workflow_step = task.workflow_current_step or "orchestrator"
        if task.status not in {"done", "cancelled"}:
            task.status = "blocked"
            task.blocked_reason = reason
            self.tasks.save(task)
        self.records.create_system_run(
            task,
            workflow_step=workflow_step,
            outcome="blocked",
            detail=reason,
            attention_trigger=attention_trigger,
        )
        return task

    def release_task(self, task_id: str) -> None:
        """Drop this engine's lease on one task without changing its status.

        Used when a command stops work on a task that must stay exactly as it
        is — a paused engine leaves the task ``in_progress`` and resumable, but
        it must not keep holding the lease while it sits idle, or nothing else
        could ever pick the task up.
        """

        task = self.store.get_task(task_id)
        if task is None:
            return
        project = self.store.get_project(task.project_id)
        if project is not None:
            self.leases.release(task, project)

    def forgive_step_visit(self, task_id: str) -> None:
        """Take back the visit a step was charged when it was interrupted on request.

        A step a person interrupted to steer it did not get to finish; counting
        it would let three or four notes use up the step's visit limit.
        """

        task = self.store.get_task(task_id)
        if task is None or not task.workflow_current_step:
            return
        counts = dict(task.step_visit_counts)
        if counts.get(task.workflow_current_step, 0) > 0:
            counts[task.workflow_current_step] -= 1
            task.step_visit_counts = counts
            self.tasks.save(task)

    def run_task(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
    ) -> Task:
        """Run one task from the workflow entry step, heartbeating its lease throughout."""

        token = self.leases.token_for(task.id)
        if token is not None:
            self.leases.start_heartbeat(task, project, token)
        try:
            return self._run_leased_task(project, workflow, task)
        finally:
            self.leases.stop_heartbeat(task.id)

    def _run_leased_task(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
    ) -> Task:
        """Run one task from the workflow entry step."""

        current_task = self.store.get_task(task.id)
        if current_task is None:
            raise OrchestratorError(f"Unknown task {task.id!r}.")
        if current_task.status in {"done", "cancelled"}:
            return current_task

        # Verify this orchestrator holds a valid lease on the task.
        active_lease = self.store.get_active_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=current_task.id,
        )
        if active_lease is None or active_lease.holder_id != self.holder_id:
            raise OrchestratorError(
                f"Task {task.id!r} is not leased by this orchestrator. "
                f"Use select_next_task() to acquire a task lease first."
            )

        active_runs = self.store.list_runs(task_id=current_task.id, status="running")
        if active_runs:
            recoverable_runs = [
                run for run in active_runs if self.recovery.run_is_stale(project, run)
            ]
            if recoverable_runs:
                self.recovery.recover_stale_running_runs(project, current_task, recoverable_runs)
                current_task = self.store.get_task(task.id) or current_task
                active_runs = self.store.list_runs(task_id=current_task.id, status="running")
            if active_runs:
                raise OrchestratorError(
                    f"Task {task.id!r} already has an active run and cannot be started again yet."
                )
        resume_step = workflow.entry_step
        resume_carried_output: str | None = None
        is_resuming = current_task.workflow_current_step is not None

        if current_task.status == "blocked":
            if current_task.workflow_current_step:
                paused_step = workflow.get_step(current_task.workflow_current_step)
                if paused_step is not None and paused_step.role == "_builtin:human_gate":
                    raise OrchestratorError(
                        f"Task {task.id!r} is paused at a human gate and must be resumed with "
                        f"`foreman approve` or `foreman deny`."
                    )
            if current_task.blocked_reason == QUESTION_BLOCKED_REASON:
                raise OrchestratorError(
                    f"Task {task.id!r} waits for an answer to its agent's question: answer it "
                    f"with `foreman task answer {task.task_key or task.id}` or on the task page."
                )
            raise OrchestratorError(
                f"Task {task.id!r} is blocked and cannot be run until it is resumed or unblocked."
            )

        if is_resuming:
            persisted_step = workflow.get_step(current_task.workflow_current_step or "")
            if persisted_step is None:
                raise OrchestratorError(
                    f"Task {task.id!r} cannot resume from unknown step "
                    f"{current_task.workflow_current_step!r}."
                )
            resume_step = persisted_step.id
            resume_carried_output = current_task.workflow_carried_output

        # Every task gets its own branch and worktree from the engine, in both
        # selection modes (ADR-0012). In autonomous mode the agent chooses what
        # to work on, not where: without a worktree it would run in the
        # operator's checkout and commit to whatever is checked out there.
        current_task.branch_name = current_task.branch_name or generate_branch_name(
            current_task
        )
        self.task_worktrees.ensure(project, current_task)

        current_task.status = "in_progress"
        current_task.blocked_reason = None
        current_task.workflow_current_step = None
        current_task.workflow_carried_output = None
        if not is_resuming:
            current_task.step_visit_counts = {}
        current_task.started_at = current_task.started_at or utc_now_text()
        self.tasks.save(current_task)

        # No try/finally around the workflow: the engine never changes what is
        # checked out in the operator's repository, so there is no branch to
        # restore when a task ends, pauses, or fails.
        self.runner.run_from_step(
            project,
            workflow,
            current_task,
            step=resume_step,
            carried_output=resume_carried_output,
        )
        refreshed = self.store.get_task(current_task.id)
        if refreshed is None:
            raise OrchestratorError(f"Task {current_task.id!r} disappeared during execution.")
        latest_run = self.store.get_latest_run(refreshed.id)
        if latest_run is not None:
            self.runner.write_runtime_context(
                latest_run,
                project,
                context_projection=build_project_context(
                    self.store,
                    project,
                    current_task=refreshed,
                    carried_output=refreshed.workflow_carried_output,
                    mirror_dirs=context_mirror_dirs(project, refreshed),
                ),
            )
        return refreshed
