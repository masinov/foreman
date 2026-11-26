"""The resident engine: status, start, stop, queued commands."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ...services.engine import (
    ENGINE_COMMAND_LIMIT,
)
from ..schemas import AgentStart, EngineCommandBody, body_as
from ..context import (
    ApiContext,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/projects/{project_id}/agent/status")
    def agent_status(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.engine.agent_status(project_id))

    @router.post("/projects/{project_id}/agent/start")
    def start_agent(
        project_id: str, body: AgentStart = Depends(body_as(AgentStart))
    ) -> dict[str, Any]:
        task_id = body.task_id or None
        requested_by = body.requested_by or None
        return with_api(
            lambda api: api.engine.start_agent(
                project_id, task_id=task_id, requested_by=requested_by
            )
        )

    @router.get("/projects/{project_id}/engine/commands")
    def list_engine_commands(
        project_id: str,
        limit: int = ENGINE_COMMAND_LIMIT,
        status: str | None = None,
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.engine.list_engine_commands(project_id, limit=limit, status=status)
        )

    @router.post("/projects/{project_id}/engine/commands")
    def send_engine_command(
        project_id: str, body: EngineCommandBody = Depends(body_as(EngineCommandBody))
    ) -> dict[str, Any]:
        requested_by = body.requested_by or None
        return with_api(
            lambda api: api.engine.send_engine_command(
                project_id, command=body.command.strip(), requested_by=requested_by
            )
        )

    return router
