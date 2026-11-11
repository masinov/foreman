"""Projects, their settings and policy."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..context import (
    ApiContext,
    read_json_body,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/projects")
    async def list_projects() -> dict[str, Any]:
        return with_api(lambda api: api.list_projects())

    @router.post("/projects")
    async def create_project(request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        return with_api(
            lambda api: api.create_project(
                name=str(data.get("name", "")),
                repo_path=str(data.get("repo_path", "")),
                workflow_id=str(data.get("workflow_id", "development")),
            )
        )

    @router.get("/projects/{project_id}")
    async def get_project(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_project(project_id))

    @router.get("/projects/{project_id}/settings")
    async def get_project_settings(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_project_settings(project_id))

    @router.get("/projects/{project_id}/policy")
    async def get_project_policy(project_id: str, task_id: str | None = None) -> dict[str, Any]:
        return with_api(lambda api: api.get_project_policy(project_id, task_id=task_id))

    @router.patch("/projects/{project_id}/settings")
    async def update_project_settings(project_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        return with_api(
            lambda api: api.update_project_settings(project_id, updates=data)
        )

    return router
