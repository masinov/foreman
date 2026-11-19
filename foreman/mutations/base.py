"""What every change shares: its error, who made it and from where, and its
audit event.

``MutationBase`` holds the surface (``via``), the actor, the role recorded
on events, the proposal being applied, and the helpers every part uses: the
audit event, the attention turn, the refusal while an engine runs the task,
and removing a finished task's worktree.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..domain.errors import ForemanError
from ..domain.models import (
    Event,
    Project,
    Run,
    Task,
)
from ..domain.policy import PolicyMatrix
from ..notifications import NotificationDispatcher
from ..repo.worktrees import WorktreeError, WorktreeManager
from ..store import ForemanStore

_RESOLVED_TASK_STATUSES = frozenset({"done", "cancelled"})


#: Task statuses that mean "not started": the only ones that may go back to
#: the backlog from a sprint.
_NOT_STARTED_STATUSES: tuple[str, ...] = ("triage", "todo")


def slug_id(prefix: str, title: str, exists: Callable[[str], object | None]) -> str:
    """Return ``<prefix>-<slug of title>``, numbered when already taken."""

    normalized = unicodedata.normalize("NFKD", title.strip().lower())
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:48] or "untitled"
    candidate = f"{prefix}-{slug}"
    suffix = 2
    while exists(candidate) is not None:
        candidate = f"{prefix}-{slug}-{suffix}"
        suffix += 1
    return candidate


class MutationError(ForemanError):
    """A requested change is not allowed. The message says why."""


class MutationBase:
    """Who is changing what, and the record every change leaves."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        via: str,
        actor: str | None = None,
        role: str = "human",
        now: Callable[[], datetime] | None = None,
        proposal_id: str | None = None,
        defer_side_effects: bool = False,
    ) -> None:
        self.store = store
        self.via = via
        self.actor = actor
        self.role = role
        self.proposal_id = proposal_id
        self.defer_side_effects = defer_side_effects
        self.deferred: list[Callable[[], str | None]] = []
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _attention(self, task: Task, project: Project, *, trigger: str, run_id: str) -> Event:
        """Raise one attention turn for a task that waits for a person."""

        now = self._now()
        notify = (
            PolicyMatrix.for_project(project)
            .resolve("notification", task_type=task.task_type, overrides=task.executor_overrides)
            .value
        )
        event = self.store.save_event(
            Event(
                id=f"evt-attention-{now.strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex[:8]}",
                run_id=run_id,
                task_id=task.id,
                project_id=project.id,
                event_type="engine.attention_needed",
                role_id=self.role,
                timestamp=now.isoformat(),
                payload={"trigger": trigger, "task_id": task.id, "notify": notify},
            )
        )
        # Queue only; the delivery worker sends. The dispatcher never raises.
        NotificationDispatcher(self.store).consider(event)
        return event

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
        if self.defer_side_effects:
            self.deferred.append(lambda: self._remove_worktree(project, recorded))
            task.worktree_path = None
            return recorded, None
        warning = self._remove_worktree(project, recorded)
        if warning is not None:
            return None, warning
        task.worktree_path = None
        return recorded, None

    @staticmethod
    def _remove_worktree(project: Project, recorded: str) -> str | None:
        """Remove one worktree; return a warning when that failed."""

        try:
            WorktreeManager(project).remove_path(Path(recorded))
        except (WorktreeError, OSError) as exc:
            return (
                f"Warning: could not remove worktree {recorded}: {exc}. "
                f"Run `foreman worktree prune {project.id}` to clean it up."
            )
        return None

    def _audit(self, task: Task, event_type: str, *, step: str, **payload: object) -> Event:
        """Record who changed a task, on a run that names the surface."""

        now = self._now()
        # Several tasks change in one operation (planning), so the stamp alone
        # does not make the ids unique, and neither does a prefix of task ids
        # that share their first words.
        stamp = f"{now.strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex[:8]}"
        runs = self.store.list_runs(task_id=task.id)
        if runs:
            run_id = runs[-1].id
        else:
            timestamp_text = now.isoformat()
            run = Run(
                id=f"run-{step}-{stamp}-{task.id[:8]}",
                task_id=task.id,
                project_id=task.project_id,
                role_id=self.role,
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
            role_id=self.role,
            timestamp=now.isoformat(),
            payload={
                "task_key": task.task_key,
                "via": self.via,
                "by": self.actor,
                **({"proposal_id": self.proposal_id} if self.proposal_id else {}),
                **{key: value for key, value in payload.items() if value is not None},
            },
        )
        self.store.save_event(event)
        return event
