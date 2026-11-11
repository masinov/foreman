"""Per-task worktrees."""

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

    @router.get("/projects/{project_id}/worktrees")
    async def list_worktrees(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.list_worktrees(project_id))

    @router.post("/projects/{project_id}/worktrees/prune")
    async def prune_worktrees(project_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        requested_by = data.get("requested_by") or None
        return with_api(
            lambda api: api.prune_worktrees(project_id, requested_by=requested_by)
        )

    return router
