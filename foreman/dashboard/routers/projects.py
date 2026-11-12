"""Projects, their settings and policy, and the views across them:
the workspace, what waits for a person, and milestones."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from ...dashboard_service import STREAM_BATCH_LIMIT

from ..streaming import event_stream_response
from ..schemas import ProjectCreate, body_as
from ..context import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    ApiContext,
    split_values,
    read_json_body,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/projects")
    def list_projects() -> dict[str, Any]:
        return with_api(lambda api: api.list_projects())

    @router.post("/projects")
    def create_project(body: ProjectCreate = Depends(body_as(ProjectCreate))) -> dict[str, Any]:
        return with_api(
            lambda api: api.create_project(
                name=body.name,
                repo_path=body.repo_path,
                workflow_id=body.workflow_id,
            )
        )

    @router.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_project(project_id))

    @router.get("/projects/{project_id}/settings")
    def get_project_settings(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_project_settings(project_id))

    @router.get("/projects/{project_id}/workflow")
    def get_project_workflow(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_project_workflow(project_id))

    @router.get("/workflows")
    def list_workflows() -> dict[str, Any]:
        return with_api(lambda api: api.list_workflows())

    @router.get("/projects/{project_id}/policy")
    def get_project_policy(project_id: str, task_id: str | None = None) -> dict[str, Any]:
        return with_api(lambda api: api.get_project_policy(project_id, task_id=task_id))

    @router.patch("/projects/{project_id}/settings")
    def update_project_settings(project_id: str, data: dict[str, Any] = Depends(read_json_body)) -> dict[str, Any]:
        return with_api(
            lambda api: api.update_project_settings(project_id, updates=data)
        )

    @router.get("/projects/{project_id}/stream")
    async def stream_project_events(
        project_id: str,
        request: Request,
        after: str | None = None,
    ) -> StreamingResponse:
        """Follow every event of a project, across its sprints and tasks.

        Without a cursor the stream starts with the most recent events, then
        continues live. ``after`` or ``Last-Event-ID`` resumes after an event.
        """

        with_api(lambda api: api.get_project(project_id))
        return event_stream_response(
            ctx,
            request,
            after=after,
            next_messages=lambda api, last_event_id: api.list_project_stream_messages(
                project_id,
                limit=STREAM_BATCH_LIMIT,
                after_event_id=last_event_id,
            ),
        )


    @router.get("/workspace")
    def get_workspace() -> dict[str, Any]:
        return with_api(lambda api: api.get_workspace())

    @router.get("/needs-you")
    def list_needs_you(
        limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return with_api(lambda api: api.list_needs_you(limit=limit, offset=offset))

    @router.get("/projects/{project_id}/needs-you")
    def list_project_needs_you(
        project_id: str,
        limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.list_needs_you(project_id=project_id, limit=limit, offset=offset)
        )

    @router.get("/milestones")
    def list_milestones(
        kind: list[str] = Query(default=[]),
        limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        kinds = split_values(kind)
        return with_api(
            lambda api: api.list_milestones(kinds=kinds, limit=limit, offset=offset)
        )

    @router.get("/projects/{project_id}/milestones")
    def list_project_milestones(
        project_id: str,
        kind: list[str] = Query(default=[]),
        limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        kinds = split_values(kind)
        return with_api(
            lambda api: api.list_milestones(
                project_id=project_id, kinds=kinds, limit=limit, offset=offset
            )
        )

    return router
