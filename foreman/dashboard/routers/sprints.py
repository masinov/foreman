"""Sprints, their tasks, their events and the live event stream."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from ...dashboard_service import (
    ACTIVITY_EVENT_LIMIT,
    STREAM_BATCH_LIMIT,
    DashboardValidationError,
)
from ..streaming import event_stream_response
from ..schemas import SprintCreate, TaskCreate, body_as
from ..context import (
    MAX_EVENTS_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    split_values,
    ApiContext,
    read_json_body,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/projects/{project_id}/sprints")
    def list_project_sprints(
        project_id: str,
        status: list[str] = Query(default=[]),
        q: str | None = None,
        limit: int | None = Query(default=None, ge=1, le=MAX_PAGE_LIMIT),
        offset: int = Query(default=0, ge=0),
        order: str = "queue",
    ) -> dict[str, Any]:
        statuses = split_values(status)
        return with_api(
            lambda api: api.list_project_sprints(
                project_id,
                statuses=statuses,
                query=q,
                limit=limit,
                offset=offset,
                order=order,
            )
        )

    @router.post("/projects/{project_id}/sprints")
    def create_sprint(
        project_id: str, body: SprintCreate = Depends(body_as(SprintCreate))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.create_sprint(
                project_id,
                title=body.title,
                goal=body.goal,
                initial_tasks=body.initial_tasks,
            )
        )

    @router.get("/sprints/{sprint_id}")
    def get_sprint(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_sprint(sprint_id))

    @router.get("/sprints/{sprint_id}/tasks")
    def list_sprint_tasks(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.list_sprint_tasks(sprint_id))

    @router.post("/sprints/{sprint_id}/tasks")
    def create_task(
        sprint_id: str, body: TaskCreate = Depends(body_as(TaskCreate))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.create_task(
                sprint_id,
                title=body.title,
                task_type=body.task_type,
                acceptance_criteria=body.acceptance_criteria,
                description=body.description,
                complexity=body.complexity or None,
                depends_on=body.depends_on,
            )
        )

    @router.get("/sprints/{sprint_id}/events")
    def list_sprint_events(
        sprint_id: str,
        limit: str = str(ACTIVITY_EVENT_LIMIT),
        after: str | None = None,
        before: str | None = None,
        type: list[str] = Query(default=[]),
    ) -> dict[str, Any]:
        event_types = split_values(type)
        try:
            parsed_limit = int(limit)
        except ValueError as exc:
            raise DashboardValidationError("Invalid limit") from exc
        if parsed_limit < 1:
            raise DashboardValidationError("Invalid limit")
        parsed_limit = min(parsed_limit, MAX_EVENTS_PAGE_LIMIT)
        return with_api(
            lambda api: api.list_sprint_events(
                sprint_id,
                limit=parsed_limit,
                after_event_id=after,
                before_event_id=before,
                event_types=event_types or None,
            )
        )

    @router.get("/sprints/{sprint_id}/stream")
    async def stream_sprint_events(
        sprint_id: str,
        request: Request,
        after: str | None = None,
    ) -> StreamingResponse:
        with_api(lambda api: api.get_sprint(sprint_id))

        return event_stream_response(
            ctx,
            request,
            after=after,
            next_messages=lambda api, last_event_id: api.list_sprint_stream_messages(
                sprint_id,
                limit=STREAM_BATCH_LIMIT,
                after_event_id=last_event_id,
            ),
        )

    @router.delete("/sprints/{sprint_id}")
    def delete_sprint(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.delete_sprint(sprint_id))

    @router.patch("/sprints/{sprint_id}")
    def patch_sprint(sprint_id: str, data: dict[str, Any] = Depends(read_json_body)) -> dict[str, Any]:
        if "status" in data:
            target_status = data["status"]
            return with_api(
                lambda api: api.transition_sprint(sprint_id, target_status=str(target_status))
            )
        field_updates = {k: v for k, v in data.items()}
        return with_api(lambda api: api.update_sprint_fields(sprint_id, updates=field_updates))

    return router
