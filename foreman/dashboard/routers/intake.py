"""The endpoint other systems file work through (ADR-0013)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ...dashboard_service import (
    DashboardService,
    DashboardValidationError,
)
from ..context import (
    ApiContext,
    presented_token,
    read_json_body,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.post("/projects/{project_id}/intake")
    async def intake_task(project_id: str, request: Request) -> Response:
        """Accept work from another system (MANUAL "Intake API").

        The only ``/api`` route authenticated by a project API token rather
        than the dashboard's shared token. 201 when the task is new, 200 when
        the same ``(source.system, source.external_ref)`` was already filed.
        """

        data = await read_json_body(request)
        source = data.get("source")
        if source is not None and not isinstance(source, dict):
            raise DashboardValidationError("'source' must be an object.")
        sprint_id = data.get("sprint_id")

        def _intake(api: DashboardService) -> dict[str, Any]:
            token = api.authenticate_intake(project_id, presented_token(request))
            return api.intake_task(
                project_id,
                token=token,
                title=str(data.get("title", "")),
                description=data.get("description"),
                acceptance_criteria=data.get("acceptance_criteria"),
                task_type=str(data.get("task_type", "fix")),
                priority=data.get("priority") or 0,
                complexity=data.get("complexity") or None,
                source=source,
                sprint_id=str(sprint_id) if sprint_id else None,
            )

        payload = with_api(_intake)
        return JSONResponse(payload, status_code=201 if payload["created"] else 200)

    return router
