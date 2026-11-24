"""How records are shown: the plain dicts the API and the CLI return."""

from __future__ import annotations

from typing import Any

from ..domain.models import Event, Task
from ..engine.control import EngineStateView


def serialize_engine_state(engine: EngineStateView) -> dict[str, Any]:
    """Serialize the engine view shared by the status route and project payloads."""

    task = engine.current_task
    return {
        "resident": engine.resident,
        "paused": engine.paused,
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
