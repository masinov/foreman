"""Reading a project's backlog (ADR-0021), for the API and the CLI alike.

Changes to the backlog go through ``foreman.mutations``; this module only
reads it, so ``GET /projects/{id}/backlog`` and ``foreman backlog list
--json`` return the same document.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .errors import ForemanError
from .models import BACKLOG_STATES, Project, Task
from .policy import PolicyMatrix
from .store import ForemanStore

#: Default page size: the design caps the backlog list at 25.
BACKLOG_PAGE_LIMIT = 25

#: What the list shows when no state is asked for: work still waiting.
DEFAULT_BACKLOG_STATES: tuple[str, ...] = ("filed", "accepted")


class BacklogQueryError(ForemanError):
    """A backlog read asked for something that does not exist."""


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


def backlog_state(task: Task) -> str | None:
    """``filed``, ``accepted`` or ``declined`` for a backlog task's status."""

    return next((name for name, status in BACKLOG_STATES.items() if status == task.status), None)


def serialize_backlog_task(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "task_key": task.task_key,
        "title": task.title,
        "state": backlog_state(task),
        "status": task.status,
        "task_type": task.task_type,
        "priority": task.priority,
        "complexity": task.complexity,
        "description": task.description,
        "acceptance_criteria": task.acceptance_criteria,
        "created_by": task.created_by,
        "created_at": task.created_at,
        "source": task_source(task),
    }


def read_backlog(
    store: ForemanStore,
    project: Project,
    *,
    states: Sequence[str] | None = None,
    query: str | None = None,
    limit: int | None = BACKLOG_PAGE_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Return one page of a project's backlog: filed first, then accepted.

    ``states`` picks among ``filed``, ``accepted`` and ``declined``; without
    it, declined work is left out. ``total`` counts every match before
    paging, ``counts`` is the whole backlog by state, and ``triage`` says
    who accepts filed work in this project (``human`` or ``auto``).
    """

    unknown = sorted(set(states or ()) - set(BACKLOG_STATES))
    if unknown:
        raise BacklogQueryError(
            f"status: unknown {', '.join(unknown)}; expected {', '.join(BACKLOG_STATES)}."
        )
    chosen = set(states or DEFAULT_BACKLOG_STATES)
    tasks, total, counts = store.page_backlog_tasks(
        project.id,
        statuses=[status for state, status in BACKLOG_STATES.items() if state in chosen],
        query=(query or "").strip() or None,
        limit=limit,
        offset=offset,
    )
    backlog = store.get_backlog(project.id)
    return {
        "project_id": project.id,
        "backlog_id": backlog.id if backlog is not None else None,
        "triage": PolicyMatrix.for_project(project).resolve("triage").value,
        "counts": {state: counts[status] for state, status in BACKLOG_STATES.items()},
        "tasks": [serialize_backlog_task(task) for task in tasks],
        "total": total,
    }
