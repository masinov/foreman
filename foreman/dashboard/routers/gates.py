"""Decision gates raised by the manager."""

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

    @router.post("/projects/{project_id}/gates")
    async def create_gate(project_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        return with_api(lambda api: api.create_gate(
            project_id,
            sprint_id=str(data.get("sprint_id", "")),
            conflict_description=str(data.get("conflict_description", "")),
            suggested_order=data.get("suggested_order") or [],
            suggested_reason=str(data.get("suggested_reason", "")),
        ))

    @router.get("/projects/{project_id}/gates")
    async def list_gates(project_id: str, status: str | None = None) -> dict[str, Any]:
        return with_api(lambda api: api.list_gates(project_id, status=status))

    @router.patch("/gates/{gate_id}")
    async def resolve_gate(gate_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        resolution = str(data.get("resolution", ""))
        resolved_by = str(data.get("resolved_by", "human"))
        return with_api(lambda api: api.resolve_gate(gate_id, resolution=resolution, resolved_by=resolved_by))

    return router
