"""How records are shown: the plain dicts the API and the CLI return."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..domain.models import Task
from ..engine.control import EngineStateView


def stable_slug(text: str) -> str:
    """Return a filesystem-safe ASCII slug from arbitrary text."""
    normalized = unicodedata.normalize("NFKD", text.strip().lower())
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug[:48] or "untitled"


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
