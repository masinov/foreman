"""Changes a person makes to tasks and sprints, in one place.

The CLI and the dashboard both let a person accept, block, unblock, cancel
and delete tasks and move sprints through their lifecycle. They used to
carry their own copies of the rules, which had drifted apart, and only some
dashboard actions left a trace. ``Mutations`` is the single implementation:
it checks the change is allowed, refuses what a running engine is in the
middle of, writes it, and records an audit event saying who did it and from
where.

Surfaces translate ``MutationError`` into their own error type and decide
how to present the result. Nothing here prints or knows about HTTP.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .engine_control import blocked_kind, resolve_gate_steps
from .errors import ForemanError
from .models import Event, Run, Sprint, SprintStatus, Task
from .store import ForemanStore
from .worktrees import WorktreeError, WorktreeManager

#: Where a sprint may go from each status.
SPRINT_TRANSITIONS: dict[str, tuple[SprintStatus, ...]] = {
    "planned": ("active", "cancelled"),
    "active": ("completed", "cancelled"),
    "completed": (),
    "cancelled": (),
}

_RESOLVED_TASK_STATUSES = frozenset({"done", "cancelled"})


class MutationError(ForemanError):
    """A requested change is not allowed. The message says why."""


@dataclass(frozen=True)
class TaskRemoval:
    """What cancelling or deleting a task did to its worktree."""

    task: Task
    removed_worktree: str | None = None
    warning: str | None = None
    changed: bool = True


class Mutations:
    """Operator changes to the tasks and sprints of one store.

    ``via`` names the surface (``"cli"``, ``"dashboard"``) and ``actor`` the
    person, when known; both are recorded on every audit event.
    """

    def __init__(
        self,
        store: ForemanStore,
        *,
        via: str,
        actor: str | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.via = via
        self.actor = actor
        self._now = now or (lambda: datetime.now(timezone.utc))

    # ── tasks ────────────────────────────────────────────────────────────

    def accept_task(self, task: Task) -> Task:
        """Move a task out of triage into the runnable queue."""

        if task.status != "triage":
            raise MutationError(
                f"Cannot accept a task with status '{task.status}'; only tasks in "
                "triage can be accepted."
            )
        task.status = "todo"
        self.store.save_task(task)
        self._audit(task, "human.task_accepted", step="triage", from_status="triage")
        return task

    def block_task(self, task: Task, reason: str) -> Task:
        """Park a task. An engine running it stops when its current step ends."""

        if task.status in _RESOLVED_TASK_STATUSES:
            raise MutationError(f"Task {task.id} cannot be blocked from status {task.status}.")
        from_status = task.status
        task.status = "blocked"
        task.blocked_reason = reason
        task.completed_at = None
        self.store.save_task(task)
        self._audit(task, "human.task_blocked", step="block", from_status=from_status, reason=reason)
        return task

    def unblock_task(self, task: Task) -> Task:
        """Return a blocked task to the queue, starting its workflow over."""

        if task.status != "blocked":
            raise MutationError(f"Task {task.id} is not blocked.")
        project = self.store.get_project(task.project_id)
        gates = resolve_gate_steps(project.workflow_id if project is not None else None)
        if blocked_kind(task, gates) == "gate":
            raise MutationError(
                f"Task {task.id} is paused at a workflow gate; use `foreman approve` "
                "or `foreman deny` instead."
            )
        reason = task.blocked_reason
        task.status = "todo"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.step_visit_counts = {}
        task.completed_at = None
        self.store.save_task(task)
        self._audit(
            task, "human.task_unblocked", step="unblock", from_status="blocked", reason=reason
        )
        return task

    def cancel_task(self, task: Task) -> TaskRemoval:
        """Cancel a task and remove its worktree. Cancelling twice changes nothing."""

        if task.status == "done":
            raise MutationError(f"Task {task.id} is already done and cannot be cancelled.")
        if task.status == "cancelled":
            return TaskRemoval(task=task, changed=False)
        self._refuse_if_running(task, "cancel")
        from_status = task.status
        task.status = "cancelled"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.completed_at = self._now().isoformat()
        removed, warning = self._discard_worktree(task)
        self.store.save_task(task)
        self._audit(task, "human.task_cancelled", step="cancel", from_status=from_status)
        return TaskRemoval(task=task, removed_worktree=removed, warning=warning)

    def delete_task(self, task: Task) -> TaskRemoval:
        """Delete a task with its history and its worktree.

        There is no audit event: the events of a deleted task are deleted
        with it.
        """

        self._refuse_if_running(task, "delete")
        removed, warning = self._discard_worktree(task)
        self.store.delete_task(task.id)
        return TaskRemoval(task=task, removed_worktree=removed, warning=warning)

    # ── sprints ──────────────────────────────────────────────────────────

    def transition_sprint(self, sprint: Sprint, target_status: str) -> Sprint:
        """Move a sprint to ``target_status``. Moving it where it already is changes nothing."""

        if sprint.status == target_status:
            return sprint
        allowed = SPRINT_TRANSITIONS.get(sprint.status, ())
        if target_status not in allowed:
            raise MutationError(
                f"Cannot transition sprint from '{sprint.status}' to '{target_status}'. "
                f"Allowed: {list(allowed) or 'none'}."
            )
        if target_status == "active":
            active = self.store.get_active_sprint(sprint.project_id)
            if active is not None and active.id != sprint.id:
                raise MutationError(
                    f"Sprint '{active.title}' is already active. "
                    "Complete or cancel it before activating another sprint."
                )
        if target_status == "completed":
            unresolved = [
                task.task_key or task.id
                for task in self.store.list_tasks(sprint_id=sprint.id)
                if task.status not in _RESOLVED_TASK_STATUSES
            ]
            if unresolved:
                raise MutationError(
                    "Sprint cannot be completed while unresolved tasks remain: "
                    + ", ".join(unresolved)
                    + ". Finish or cancel them, or cancel the sprint."
                )
        now = self._now().isoformat()
        sprint.status = target_status  # type: ignore[assignment]
        if target_status == "active":
            sprint.started_at = sprint.started_at or now
            sprint.completed_at = None
        if target_status in ("completed", "cancelled"):
            sprint.started_at = sprint.started_at or (now if target_status == "completed" else None)
            sprint.completed_at = now
        self.store.save_sprint(sprint)
        return sprint

    def delete_sprint(self, sprint: Sprint) -> None:
        """Delete a sprint with its tasks, runs and events."""

        for task in self.store.list_tasks(sprint_id=sprint.id):
            self._refuse_if_running(task, "delete")
        self.store.delete_sprint(sprint.id)

    # ── shared ───────────────────────────────────────────────────────────

    def _refuse_if_running(self, task: Task, verb: str) -> None:
        """Refuse a change to a task an engine is executing right now.

        The engine would overwrite the row with its next save, or keep
        working on a task that no longer exists. It has to stop first.
        """

        running = self.store.list_runs(task_id=task.id, status="running")
        if running and self.store.get_engine_lock(task.project_id) is not None:
            raise MutationError(
                f"Task {task.id} has a running agent step ({running[0].id}). Stop it "
                f"first with `foreman engine stop-task {task.project_id} {task.id}` "
                f"(or Stop in the dashboard), then {verb} it."
            )

    def _discard_worktree(self, task: Task) -> tuple[str | None, str | None]:
        """Remove a finished task's worktree. Returns (removed path, warning).

        Failing to remove it must not fail the change: the row is what
        matters, and `foreman worktree prune` can clean up later.
        """

        recorded = task.worktree_path
        if not recorded:
            return None, None
        project = self.store.get_project(task.project_id)
        if project is None:
            return None, None
        try:
            WorktreeManager(project).remove_path(Path(recorded))
        except (WorktreeError, OSError) as exc:
            return None, (
                f"Warning: could not remove worktree {recorded}: {exc}. "
                f"Run `foreman worktree prune {project.id}` to clean it up."
            )
        task.worktree_path = None
        return recorded, None

    def _audit(self, task: Task, event_type: str, *, step: str, **payload: object) -> Event:
        """Record that a person changed a task, on a run that names the surface."""

        now = self._now()
        stamp = now.strftime("%Y%m%d%H%M%S%f")
        runs = self.store.list_runs(task_id=task.id)
        if runs:
            run_id = runs[-1].id
        else:
            timestamp_text = now.isoformat()
            run = Run(
                id=f"run-{step}-{stamp}-{task.id[:8]}",
                task_id=task.id,
                project_id=task.project_id,
                role_id="human",
                workflow_step=step,
                agent_backend=self.via,
                status="completed",
                outcome=step,
                started_at=timestamp_text,
                completed_at=timestamp_text,
                created_at=timestamp_text,
            )
            self.store.save_run(run)
            run_id = run.id
        event = Event(
            id=f"evt-{step}-{stamp}-{task.id[:8]}",
            run_id=run_id,
            task_id=task.id,
            project_id=task.project_id,
            event_type=event_type,
            role_id="human",
            timestamp=now.isoformat(),
            payload={
                "task_key": task.task_key,
                "via": self.via,
                "by": self.actor,
                **{key: value for key, value in payload.items() if value is not None},
            },
        )
        self.store.save_event(event)
        return event
