"""Reading a project's backlog (ADR-0021), for the API and the CLI alike.

Changes to the backlog go through ``foreman.mutations.base``; this module only
reads it, so ``GET /projects/{id}/backlog`` and ``foreman backlog list
--json`` return the same document.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Callable

from ..domain.errors import ForemanError
from ..domain.models import (
    BACKLOG_STATES,
    Project,
    Sprint,
    Task,
)
from ..domain.policy import PolicyMatrix
from ..engine.limits import resolve_project_settings
from ..engine.selection import backlog_ready_for_foreman, pulled_task_ids
from ..mutations import MutationError
from ..store import ForemanStore
from .base import Service
from .errors import InvalidRequestError, NotFoundError
from .tasks import TaskService
from .views import task_source

#: Default page size: the design caps the backlog list at 25.
BACKLOG_PAGE_LIMIT = 25

#: What the list shows when no state is asked for: work still waiting.
DEFAULT_BACKLOG_STATES: tuple[str, ...] = ("filed", "accepted")


class BacklogQueryError(ForemanError):
    """A backlog read asked for something that does not exist."""


def backlog_state(task: Task) -> str | None:
    """``filed``, ``accepted`` or ``declined`` for a backlog task's status."""

    return next((name for name, status in BACKLOG_STATES.items() if status == task.status), None)


def serialize_backlog_task(
    task: Task, carried_from: dict[str, Any] | None = None
) -> dict[str, Any]:
    """One backlog row; ``carried_from`` is the sprint it was moved back from, if any."""

    return {
        "id": task.id,
        "task_key": task.task_key,
        "title": task.title,
        "state": backlog_state(task),
        "status": task.status,
        "task_type": task.task_type,
        "priority": task.priority,
        "description": task.description,
        "acceptance_criteria": task.acceptance_criteria,
        "rests_on": [ref.as_dict() for ref in task.rests_on],
        "labels": list(task.labels),
        "created_by": task.created_by,
        "created_at": task.created_at,
        "source": task_source(task),
        "carried_from": carried_from,
    }


def foreman_and_the_backlog(store: ForemanStore, project: Project) -> dict[str, Any]:
    """What Foreman may do with this project's backlog on its own (ADR-0028).

    ``starts``: whether it starts accepted backlog work itself. ``limit`` and
    ``started``: how many it may start per sprint and how many it has in the
    active sprint (``started`` is null with no active sprint). ``ready``: how
    many accepted tasks it could start next.
    """


    settings = resolve_project_settings(project)
    sprint = store.get_active_sprint(project.id)
    return {
        "starts": settings.task_selection_mode == "autonomous",
        "limit": settings.max_autonomous_tasks,
        "started": len(pulled_task_ids(store, sprint)) if sprint is not None else None,
        "ready": len(backlog_ready_for_foreman(store, project)),
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
    who accepts filed work in this project (``human`` or ``auto``). Each task's
    ``carried_from`` is ``{"id", "title"}`` of the sprint it was moved back
    from, or null when it was never planned.
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
    origins = store.backlog_unplanned_origins(project.id) if tasks else {}
    return {
        "project_id": project.id,
        "backlog_id": backlog.id if backlog is not None else None,
        "triage": PolicyMatrix.for_project(project).resolve("triage").value,
        "foreman": foreman_and_the_backlog(store, project),
        "counts": {state: counts[status] for state, status in BACKLOG_STATES.items()},
        "tasks": [serialize_backlog_task(task, origins.get(task.id)) for task in tasks],
        "total": total,
    }


class BacklogService(Service):
    """The backlog's actions: filing, declining, planning and unplanning."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        now_factory: Callable[[], datetime] | None = None,
        tasks: TaskService,
    ) -> None:
        super().__init__(store, now_factory=now_factory)
        self.tasks = tasks

    def list_backlog(
        self,
        project_id: str,
        *,
        states: Sequence[str] | None = None,
        query: str | None = None,
        limit: int = BACKLOG_PAGE_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return one page of the project's backlog (see ``foreman.services.backlog``)."""

        project = self._require_project(project_id)
        try:
            return read_backlog(
                self.store, project, states=states, query=query, limit=limit, offset=offset
            )
        except BacklogQueryError as exc:
            raise InvalidRequestError(str(exc)) from exc

    def file_backlog_task(
        self,
        project_id: str,
        *,
        title: str,
        task_type: str = "feature",
        description: str | None = None,
        acceptance_criteria: str | None = None,
        rests_on: list[Any] | None = None,
        labels: list[str] | None = None,
        priority: int = 0,
        accept: bool = False,
        requested_by: str | None = None,
    ) -> dict[str, Any]:
        """File one task a person wrote into the backlog."""

        project = self._require_project(project_id)
        try:
            filed = self._mutations(requested_by).file_task(
                project,
                title=title,
                task_type=task_type,
                description=description,
                acceptance_criteria=acceptance_criteria,
                rests_on=rests_on,
                labels=labels,
                priority=priority,
                created_by=(requested_by or "").strip() or "human",
                accept=accept,
            )
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self.tasks.get_task(filed.task.id)

    def decline_task(
        self, task_id: str, *, reason: str | None = None, requested_by: str | None = None
    ) -> dict[str, Any]:
        """Decline one filed task. It is kept, marked declined, in the backlog."""

        task = self._require_task(task_id)
        try:
            self._mutations(requested_by).decline_task(task, reason)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self.tasks.get_task(task.id)

    def plan_backlog(
        self,
        project_id: str,
        *,
        task_ids: Sequence[str],
        sprint_id: str | None = None,
        new_sprint: dict[str, Any] | None = None,
        requested_by: str | None = None,
    ) -> dict[str, Any]:
        """Plan accepted backlog tasks into a sprint, or into a new planned one."""

        self._require_project(project_id)
        if not task_ids:
            raise InvalidRequestError("'task_ids' must name at least one task.")
        if bool(sprint_id) == bool(new_sprint):
            raise InvalidRequestError(
                "Send either 'sprint_id' or 'new_sprint' ({title, goal}), not both."
            )
        tasks: list[Task] = []
        for task_id in task_ids:
            task = self._require_task(task_id)
            if task.project_id != project_id:
                raise InvalidRequestError(
                    f"Task {task_id} does not belong to this project."
                )
            tasks.append(task)
        sprint: Sprint | None = None
        if sprint_id:
            sprint = self.store.get_sprint(sprint_id)
            if sprint is None or sprint.is_backlog:
                raise NotFoundError(f"Sprint not found: {sprint_id}")
        try:
            planned = self._mutations(requested_by).plan_tasks(
                tasks,
                sprint=sprint,
                new_sprint_title=(new_sprint or {}).get("title"),
                new_sprint_goal=(new_sprint or {}).get("goal"),
            )
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return {
            "sprint": {
                "id": planned.sprint.id,
                "title": planned.sprint.title,
                "goal": planned.sprint.goal,
                "status": planned.sprint.status,
                "order_index": planned.sprint.order_index,
            },
            "created_sprint": planned.created_sprint,
            "task_ids": [task.id for task in planned.tasks],
        }

    def unplan_task(self, task_id: str, *, requested_by: str | None = None) -> dict[str, Any]:
        """Move a task that has not started back from its sprint to the backlog."""

        task = self._require_task(task_id)
        try:
            self._mutations(requested_by).unplan_task(task)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self.tasks.get_task(task.id)
