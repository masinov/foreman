"""How records are shown: the plain dicts the API and the CLI return."""

from __future__ import annotations

from typing import Any

from ..domain.holds import Hold, LevelBlock, task_hold
from ..domain.models import Event, Task
from ..engine.control import EngineStateView
from ..store import ForemanStore


def serialize_level_block(block: LevelBlock | None) -> dict[str, Any] | None:
    """A block on a sprint or the workspace (ADR-0043), or None."""

    if block is None:
        return None
    return {
        "scope": block.scope,
        "scope_id": block.scope_id,
        "reason": block.reason,
        "by": block.set_by,
        "at": block.set_at,
    }


def serialize_hold(hold: Hold | None) -> dict[str, Any] | None:
    """What keeps a task from its next step (ADR-0043), or None."""

    if hold is None:
        return None
    return {
        "scope": hold.scope,
        "kind": hold.kind,
        "mode": hold.mode,
        "by": hold.by,
        "at": hold.at,
        "reason": hold.reason,
    }


class HoldReader:
    """Reads the blocks above tasks once, for a page of tasks."""

    def __init__(self, store: ForemanStore) -> None:
        self.store = store
        self.workspace_block = store.get_workspace_block()
        self._sprint_blocks: dict[str, LevelBlock | None] = {}

    def sprint_block(self, sprint_id: str | None) -> LevelBlock | None:
        if not sprint_id:
            return None
        if sprint_id not in self._sprint_blocks:
            self._sprint_blocks[sprint_id] = self.store.get_sprint_block(sprint_id)
        return self._sprint_blocks[sprint_id]

    def hold(self, task: Task) -> dict[str, Any] | None:
        return serialize_hold(
            task_hold(
                task,
                sprint_block=self.sprint_block(task.sprint_id),
                workspace_block=self.workspace_block,
            )
        )


def serialize_engine_state(engine: EngineStateView) -> dict[str, Any]:
    """Serialize the engine view shared by the status route and project payloads."""

    task = engine.current_task
    return {
        "resident": engine.resident,
        "state": engine.state,
        "holder_id": engine.holder_id,
        "heartbeat_age_seconds": engine.heartbeat_age_seconds,
        "heartbeat_at": engine.lock.heartbeat_at if engine.lock else None,
        "lease_expires_at": engine.lock.expires_at if engine.lock else None,
        "lease_expired": engine.lease_expired,
        "current_task": (
            {
                "id": task.id,
                "task_key": task.task_key,
                "title": task.title,
                "status": task.status,
                "workflow_current_step": task.workflow_current_step,
            }
            if task is not None
            else None
        ),
    }


def task_source(task: Task) -> dict[str, Any] | None:
    """Where a task came from, or None when a person or an agent filed it."""

    if not any((task.source_system, task.source_ref, task.source_url, task.reporter)):
        return None
    return {
        "system": task.source_system,
        "external_ref": task.source_ref,
        "url": task.source_url,
        "reporter": task.reporter,
    }


def task_filed_from(store: Any, events: list[Event]) -> dict[str, Any] | None:
    """The task an agent was working on when it filed this one, or None.

    The filing event records ``filed_from_task_id`` and ``filed_from_run_id``
    (the engine's task_created signal). A task filed by a person or another
    system has neither, so none is returned. ``task_key`` and ``title`` are
    None when that task no longer exists.
    """

    for event in events:
        payload = event.payload or {}
        origin_id = payload.get("filed_from_task_id")
        if not origin_id:
            continue
        origin = store.get_task(origin_id)
        return {
            "task_id": origin_id,
            "task_key": origin.task_key if origin else None,
            "title": origin.title if origin else None,
            "run_id": payload.get("filed_from_run_id"),
            "exists": origin is not None,
        }
    return None
