"""Roles and workflows: the shipped ones, and each project's own (ADR-0024)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..context import (
    ApiContext,
    read_json_body,
)

_KINDS = {"roles": "role", "workflows": "workflow"}


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/roles")
    def list_roles() -> dict[str, Any]:
        return with_api(lambda api: api.list_roles())

    @router.get("/projects/{project_id}/definitions")
    def get_project_definitions(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_project_definitions(project_id))

    def _save(kinds: str):
        def save(
            project_id: str, definition_id: str, data: dict[str, Any] = Depends(read_json_body)
        ) -> dict[str, Any]:
            return with_api(
                lambda api: api.save_project_definition(project_id, _KINDS[kinds], definition_id, data)
            )

        return save

    def _reset(kinds: str):
        def reset(project_id: str, definition_id: str) -> dict[str, Any]:
            return with_api(
                lambda api: api.reset_project_definition(project_id, _KINDS[kinds], definition_id)
            )

        return reset

    for kinds in _KINDS:
        path = f"/projects/{{project_id}}/{kinds}/{{definition_id}}"
        router.put(path, name=f"save_project_{kinds}")(_save(kinds))
        router.delete(path, name=f"reset_project_{kinds}")(_reset(kinds))

    return router
