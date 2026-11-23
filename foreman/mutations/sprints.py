"""A sprint's lifecycle and fields: create, edit, move, finish, delete.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.models import (
    Project,
    Sprint,
    SprintStatus,
)
from .base import _RESOLVED_TASK_STATUSES, MutationBase, MutationError, slug_id
from .checkpoint import SprintCheckpoints

#: Where a sprint may go from each status.
SPRINT_TRANSITIONS: dict[str, tuple[SprintStatus, ...]] = {
    "planned": ("active", "cancelled"),
    "active": ("completed", "cancelled"),
    # A finished sprint may be reopened (owner, 2026-11-18); a cancelled one
    # may not.
    "completed": ("active",),
    "cancelled": (),
}


#: Sprint fields a person may edit outside its lifecycle.
SPRINT_EDIT_FIELDS: tuple[str, ...] = ("title", "goal", "order_index")


class SprintMutations(MutationBase):
    """Changes to sprints."""

    def transition_sprint(self, sprint: Sprint, target_status: str) -> Sprint:
        """Move a sprint to ``target_status``. Moving it where it already is changes nothing."""

        if sprint.is_backlog:
            raise MutationError(
                "The backlog is not a sprint: it cannot be activated, completed or cancelled."
            )
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
        if target_status == "completed":
            self._checkpoint(sprint)
        return sprint

    def _checkpoint(self, sprint: Sprint) -> None:
        """Tag the finished sprint, and commit its note first where asked (spec 6.4).

        Work outside the database: a proposal applies it after its changes
        are written (``defer_side_effects``).
        """

        project = self.store.get_project(sprint.project_id)
        if project is None:
            return

        def make() -> str | None:
            made = SprintCheckpoints(self.store).record(project, sprint)
            return None if made.problem is None else f"The sprint is finished but not tagged: {made.problem}"

        if self.defer_side_effects:
            self.deferred.append(make)
        else:
            make()

    def create_sprint(self, project: Project, *, title: str, goal: str | None = None) -> Sprint:
        """Create a planned sprint at the end of the project's queue."""

        clean = (title or "").strip()
        if not clean:
            raise MutationError("Sprint title is required.")
        existing = self.store.list_sprints(project.id)
        sprint = Sprint(
            id=slug_id("sprint", clean, self.store.get_sprint),
            project_id=project.id,
            title=clean,
            goal=(goal or "").strip() or None,
            status="planned",
            order_index=max((s.order_index for s in existing), default=-1) + 1,
            created_at=self._now().isoformat(),
        )
        self.store.save_sprint(sprint)
        return sprint

    def edit_sprint(self, sprint: Sprint, changes: Mapping[str, Any]) -> Sprint:
        """Change a sprint's title, goal or place in the queue (``SPRINT_EDIT_FIELDS``)."""

        if sprint.is_backlog:
            raise MutationError("The backlog is not a sprint and cannot be edited.")
        unknown = sorted(set(changes) - set(SPRINT_EDIT_FIELDS))
        if unknown:
            raise MutationError(f"Unknown sprint fields: {unknown}")
        if not changes:
            raise MutationError("No fields provided for update.")
        if "title" in changes:
            value = str(changes["title"] or "").strip()
            if not value:
                raise MutationError("Sprint title cannot be empty.")
            sprint.title = value
        if "goal" in changes:
            value = changes["goal"]
            sprint.goal = str(value).strip() or None if value else None
        if "order_index" in changes:
            try:
                sprint.order_index = int(changes["order_index"])
            except (TypeError, ValueError) as exc:
                raise MutationError("order_index must be an integer.") from exc
        self.store.save_sprint(sprint)
        return sprint

    def move_sprint(self, sprint: Sprint, direction: str) -> Sprint:
        """Move a planned sprint one place earlier (``up``) or later (``down``) in the queue.

        Only planned sprints have an order a person can change: the active one
        is running and finished ones are history. Moving the first one up or
        the last one down changes nothing. The planned sprints are renumbered
        in one transaction, so the queue never shows a half-applied order.
        """

        if direction not in ("up", "down"):
            raise MutationError("direction must be 'up' or 'down'.")
        if sprint.is_backlog:
            raise MutationError("The backlog is not a sprint and has no place in the queue.")
        if sprint.status != "planned":
            raise MutationError(
                f"Sprint '{sprint.title}' is {sprint.status}; only a planned sprint can be moved in the queue."
            )
        everything = self.store.list_sprints(sprint.project_id)
        planned = [entry for entry in everything if entry.status == "planned"]
        position = next(index for index, entry in enumerate(planned) if entry.id == sprint.id)
        target = position - 1 if direction == "up" else position + 1
        if target < 0 or target >= len(planned):
            return sprint
        planned[position], planned[target] = planned[target], planned[position]
        # Planned sprints run after everything that is not planned, so they
        # are numbered after it; this also repairs equal numbers, which
        # swapping two values would leave in place.
        first = max((entry.order_index for entry in everything if entry.status != "planned"), default=-1) + 1
        with self.store.atomic():
            for offset, entry in enumerate(planned):
                if entry.order_index != first + offset:
                    entry.order_index = first + offset
                    self.store.save_sprint(entry)
        return next(entry for entry in planned if entry.id == sprint.id)

    def delete_sprint(self, sprint: Sprint) -> None:
        """Delete a sprint with its tasks, runs and events."""

        if sprint.is_backlog:
            raise MutationError("The backlog is not a sprint and cannot be deleted.")
        for task in self.store.list_tasks(sprint_id=sprint.id):
            self._refuse_if_running(task, "delete")
        self.store.delete_sprint(sprint.id)
