"""Decision gates raised by the manager."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..schemas import GateCreate, GateResolution, body_as
from ..context import (
    ApiContext,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.post("/projects/{project_id}/gates")
    def create_gate(
        project_id: str, body: GateCreate = Depends(body_as(GateCreate))
    ) -> dict[str, Any]:
        return with_api(lambda api: api.create_gate(
            project_id,
            sprint_id=body.sprint_id,
            conflict_description=body.conflict_description,
            suggested_order=body.suggested_order or [],
            suggested_reason=body.suggested_reason,
        ))

    @router.get("/projects/{project_id}/gates")
    def list_gates(project_id: str, status: str | None = None) -> dict[str, Any]:
        return with_api(lambda api: api.list_gates(project_id, status=status))

    @router.patch("/gates/{gate_id}")
    def resolve_gate(
        gate_id: str, body: GateResolution = Depends(body_as(GateResolution))
    ) -> dict[str, Any]:
        resolution = body.resolution
        resolved_by = body.resolved_by
        return with_api(lambda api: api.resolve_gate(gate_id, resolution=resolution, resolved_by=resolved_by))

    return router
