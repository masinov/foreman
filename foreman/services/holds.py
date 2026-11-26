"""A user's holds on work, from any surface (ADR-0043).

Pause, Stop and Resume on a task, a sprint or the workspace, and Block and
Unblock of a sprint or the workspace. A task's own Block and Unblock stay
with the task service. Each answer says what changed, by task key, so a
page can say it in its toast ("Resumed FOR-66 and FOR-67.").
"""

from __future__ import annotations

from typing import Any

from ..domain.holds import LevelBlock, PAUSE_MODES
from ..mutations import MutationError
from ..mutations.holds import HoldChange
from .base import Service
from .errors import InvalidRequestError
from .views import serialize_level_block


def _serialize_change(change: HoldChange) -> dict[str, Any]:
    return {
        "task_ids": [task.id for task in change.tasks],
        "task_keys": change.task_keys,
    }


class HoldService(Service):
    """Pausing, stopping and resuming work; blocking sprints and the workspace."""

    def _mode(self, mode: str | None) -> str:
        value = (mode or "finish_step").strip()
        if value not in PAUSE_MODES:
            raise InvalidRequestError(
                f"mode: unknown {value!r}; expected {', '.join(PAUSE_MODES)}."
            )
        return value

    def _apply(self, operation):  # type: ignore[no-untyped-def]
        try:
            return operation()
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc

    # ── A task ───────────────────────────────────────────────────────────

    def pause_task(
        self, task_id: str, *, mode: str | None = None, requested_by: str | None = None
    ) -> dict[str, Any]:
        task = self._require_task(task_id)
        chosen = self._mode(mode)
        paused = self._apply(lambda: self._mutations(requested_by).pause_task(task, mode=chosen))
        return {"task_id": paused.id, "task_key": paused.task_key, "mode": chosen}

    def stop_task(self, task_id: str, *, requested_by: str | None = None) -> dict[str, Any]:
        return self.pause_task(task_id, mode="now", requested_by=requested_by)

    def resume_task(self, task_id: str, *, requested_by: str | None = None) -> dict[str, Any]:
        task = self._require_task(task_id)
        resumed = self._apply(lambda: self._mutations(requested_by).resume_task(task))
        return {"task_id": resumed.id, "task_key": resumed.task_key}

    # ── A sprint ─────────────────────────────────────────────────────────

    def pause_sprint(
        self, sprint_id: str, *, mode: str | None = None, requested_by: str | None = None
    ) -> dict[str, Any]:
        sprint = self._require_sprint(sprint_id)
        chosen = self._mode(mode)
        change = self._apply(
            lambda: self._mutations(requested_by).pause_sprint(sprint, mode=chosen)
        )
        return {"sprint_id": sprint.id, "mode": chosen, **_serialize_change(change)}

    def resume_sprint(self, sprint_id: str, *, requested_by: str | None = None) -> dict[str, Any]:
        sprint = self._require_sprint(sprint_id)
        change = self._apply(lambda: self._mutations(requested_by).resume_sprint(sprint))
        return {"sprint_id": sprint.id, **_serialize_change(change)}

    def block_sprint(
        self, sprint_id: str, *, reason: str, requested_by: str | None = None
    ) -> dict[str, Any]:
        sprint = self._require_sprint(sprint_id)
        block: LevelBlock = self._apply(
            lambda: self._mutations(requested_by).block_sprint(sprint, reason)
        )
        return {"sprint_id": sprint.id, "block": serialize_level_block(block)}

    def unblock_sprint(self, sprint_id: str, *, requested_by: str | None = None) -> dict[str, Any]:
        sprint = self._require_sprint(sprint_id)
        block = self._apply(lambda: self._mutations(requested_by).unblock_sprint(sprint))
        return {"sprint_id": sprint.id, "unblocked": serialize_level_block(block)}

    # ── The workspace ────────────────────────────────────────────────────

    def pause_all(
        self, *, mode: str | None = None, requested_by: str | None = None
    ) -> dict[str, Any]:
        chosen = self._mode(mode)
        change = self._apply(lambda: self._mutations(requested_by).pause_all(mode=chosen))
        return {"mode": chosen, **_serialize_change(change)}

    def resume_all(self, *, requested_by: str | None = None) -> dict[str, Any]:
        change = self._apply(lambda: self._mutations(requested_by).resume_all())
        return _serialize_change(change)

    def block_all(self, *, reason: str, requested_by: str | None = None) -> dict[str, Any]:
        block = self._apply(lambda: self._mutations(requested_by).block_all(reason))
        return {"block": serialize_level_block(block)}

    def unblock_all(self, *, requested_by: str | None = None) -> dict[str, Any]:
        block = self._apply(lambda: self._mutations(requested_by).unblock_all())
        return {"unblocked": serialize_level_block(block)}
