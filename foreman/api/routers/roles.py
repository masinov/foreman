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
        return with_api(lambda api: api.definitions.list_roles())

    @router.get("/definitions")
    def get_workspace_definitions() -> dict[str, Any]:
        return with_api(lambda api: api.definitions.get_project_definitions(None))

    @router.get("/projects/{project_id}/definitions")
    def get_project_definitions(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.definitions.get_project_definitions(project_id))

    def _save(kinds: str):
        def save(
            project_id: str, definition_id: str, data: dict[str, Any] = Depends(read_json_body)
        ) -> dict[str, Any]:
            return with_api(
                lambda api: api.definitions.save_project_definition(project_id, _KINDS[kinds], definition_id, data)
            )

        return save

    def _reset(kinds: str):
        def reset(project_id: str, definition_id: str) -> dict[str, Any]:
            return with_api(
                lambda api: api.definitions.reset_project_definition(project_id, _KINDS[kinds], definition_id)
            )

        return reset

    def _save_default(kinds: str):
        def save(definition_id: str, data: dict[str, Any] = Depends(read_json_body)) -> dict[str, Any]:
            return with_api(
                lambda api: api.definitions.save_project_definition(None, _KINDS[kinds], definition_id, data)
            )

        return save

    def _reset_default(kinds: str):
        def reset(definition_id: str) -> dict[str, Any]:
            return with_api(lambda api: api.definitions.reset_project_definition(None, _KINDS[kinds], definition_id))

        return reset

    for kinds in _KINDS:
        path = f"/projects/{{project_id}}/{kinds}/{{definition_id}}"
        router.put(path, name=f"save_project_{kinds}")(_save(kinds))
        router.delete(path, name=f"reset_project_{kinds}")(_reset(kinds))
        # The workspace's defaults (ADR-0024, amendment of 2026-11-16).
        default_path = f"/{kinds}/{{definition_id}}"
        router.put(default_path, name=f"save_default_{kinds}")(_save_default(kinds))
        router.delete(default_path, name=f"reset_default_{kinds}")(_reset_default(kinds))

    return router
