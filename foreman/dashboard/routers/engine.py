"""The resident engine: status, start, stop, queued commands."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ...dashboard_service import (
    ENGINE_COMMAND_LIMIT,
)
from ..context import (
    ApiContext,
    read_json_body,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/projects/{project_id}/agent/status")
    async def agent_status(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.agent_status(project_id))

    @router.post("/projects/{project_id}/agent/stop")
    async def stop_agent(project_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        requested_by = data.get("requested_by") or None
        return with_api(lambda api: api.stop_agent(project_id, requested_by=requested_by))

    @router.post("/projects/{project_id}/agent/start")
    async def start_agent(project_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        task_id = data.get("task_id") or None
        requested_by = data.get("requested_by") or None
        return with_api(
            lambda api: api.start_agent(
                project_id, task_id=task_id, requested_by=requested_by
            )
        )

    @router.get("/projects/{project_id}/engine/commands")
    async def list_engine_commands(
        project_id: str,
        limit: int = ENGINE_COMMAND_LIMIT,
        status: str | None = None,
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.list_engine_commands(project_id, limit=limit, status=status)
        )

    return router
