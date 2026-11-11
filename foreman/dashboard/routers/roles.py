"""Roles."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..context import (
    ApiContext,
    read_json_body,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/roles")
    def list_roles() -> dict[str, Any]:
        return with_api(lambda api: api.list_roles())

    @router.patch("/roles/{role_id}")
    def update_role(role_id: str, data: dict[str, Any] = Depends(read_json_body)) -> dict[str, Any]:
        return with_api(lambda api: api.update_role(role_id, updates=data))

    return router
