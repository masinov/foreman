"""The project backlog: filed and accepted work that is not in a sprint (ADR-0021)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ...backlog import BACKLOG_PAGE_LIMIT
from ..context import MAX_PAGE_LIMIT, ApiContext, split_values
from ..schemas import BacklogFile, BacklogPlan, RequestedBy, TaskDecline, body_as


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/projects/{project_id}/backlog")
    def list_backlog(
        project_id: str,
        status: list[str] = Query(default=[]),
        q: str | None = None,
        limit: int = Query(default=BACKLOG_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        states = split_values(status)
        return with_api(
            lambda api: api.list_backlog(
                project_id, states=states, query=q, limit=limit, offset=offset
            )
        )

    @router.post("/projects/{project_id}/backlog", status_code=201)
    def file_backlog_task(
        project_id: str, body: BacklogFile = Depends(body_as(BacklogFile))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.file_backlog_task(
                project_id,
                title=body.title,
                task_type=body.task_type,
                description=body.description,
                acceptance_criteria=body.acceptance_criteria,
                priority=body.priority,
                complexity=body.complexity,
                accept=body.accept,
                requested_by=body.requested_by,
            )
        )

    @router.post("/projects/{project_id}/backlog/plan")
    def plan_backlog(
        project_id: str, body: BacklogPlan = Depends(body_as(BacklogPlan))
    ) -> dict[str, Any]:
        new_sprint = body.new_sprint.model_dump() if body.new_sprint is not None else None
        return with_api(
            lambda api: api.plan_backlog(
                project_id,
                task_ids=body.task_ids,
                sprint_id=body.sprint_id,
                new_sprint=new_sprint,
                requested_by=body.requested_by,
            )
        )

    @router.post("/tasks/{task_id}/decline")
    def decline_task(
        task_id: str, body: TaskDecline = Depends(body_as(TaskDecline))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.decline_task(
                task_id, reason=body.reason, requested_by=body.requested_by
            )
        )

    @router.post("/tasks/{task_id}/unplan")
    def unplan_task(
        task_id: str, body: RequestedBy = Depends(body_as(RequestedBy))
    ) -> dict[str, Any]:
        return with_api(lambda api: api.unplan_task(task_id, requested_by=body.requested_by))

    return router
