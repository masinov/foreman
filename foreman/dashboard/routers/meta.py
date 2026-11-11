"""The manager chat."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ...dashboard_service import (
    DashboardValidationError,
)
from ...dashboard_service import DashboardNotFoundError
from ..context import (
    ApiContext,
    open_store,
    read_json_body,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()

    @router.post("/projects/{project_id}/meta/message")
    async def meta_message(project_id: str, request: Request) -> StreamingResponse:
        from ...meta_agent import process_message as meta_process_message

        ctx.require_manager()
        data = await read_json_body(request)
        message = str(data.get("message", "")).strip()
        if not message:
            raise DashboardValidationError("message cannot be empty.")

        # Validate up front; the streaming generator opens its own store so it
        # can keep state available for the full turn (history + session writes).
        with open_store(ctx.db_path) as store:
            if store.get_project(project_id) is None:
                raise DashboardNotFoundError(f"Project not found: {project_id}")

        async def _stream():
            with open_store(ctx.db_path) as store:
                project = store.get_project(project_id)
                if project is None:
                    yield (json.dumps({
                        "type": "error",
                        "message": f"Project not found: {project_id}",
                    }) + "\n").encode("utf-8")
                    return
                async for chunk in meta_process_message(
                    project_id,
                    message,
                    store=store,
                    project=project,
                ):
                    yield chunk.encode("utf-8")

        return StreamingResponse(
            _stream(),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no"},
        )

    @router.get("/projects/{project_id}/meta/history")
    def meta_history(
        project_id: str,
        limit: int = 50,
        before: str | None = None,
    ) -> dict[str, Any]:
        from ...meta_agent import get_history as meta_get_history

        with open_store(ctx.db_path) as store:
            if store.get_project(project_id) is None:
                raise DashboardNotFoundError(f"Project not found: {project_id}")
            turns, has_more = meta_get_history(
                store, project_id, limit=limit, before_id=before
            )
        return {
            "project_id": project_id,
            "turns": turns,
            "has_more": has_more,
        }

    @router.delete("/projects/{project_id}/meta/session")
    def clear_meta_session(project_id: str) -> dict[str, Any]:
        from ...meta_agent import clear_session as meta_clear_session

        ctx.require_manager()
        with open_store(ctx.db_path) as store:
            if store.get_project(project_id) is None:
                raise DashboardNotFoundError(f"Project not found: {project_id}")
            meta_clear_session(store, project_id)
        return {"project_id": project_id, "cleared": True}

    @router.post("/projects/{project_id}/meta/supervise")
    async def meta_supervise(project_id: str, request: Request):
        from ...meta_agent import process_message as meta_process_message
        from ...digest import build_attention_digest

        ctx.require_manager()
        data = await read_json_body(request)
        event_id = str(data.get("event_id", "")).strip()
        if not event_id:
            raise DashboardValidationError("event_id is required.")

        # Validate and run the idempotency check up front, before streaming.
        with open_store(ctx.db_path) as store:
            project = store.get_project(project_id)
            if project is None:
                raise DashboardNotFoundError(f"Project not found: {project_id}")
            event = store.get_event(event_id)
            if (
                event is None
                or event.project_id != project_id
                or event.event_type != "engine.attention_needed"
            ):
                raise DashboardValidationError(
                    "event_id must reference an engine.attention_needed event "
                    "for this project."
                )
            if store.has_consumed_supervision_event(project_id, event_id):
                return JSONResponse(
                    {"error": "supervision event already consumed"},
                    status_code=409,
                )
            trigger = str(event.payload.get("trigger", "task_blocked"))
            task_id = event.payload.get("task_id")

        async def _stream():
            with open_store(ctx.db_path) as store:
                project = store.get_project(project_id)
                if project is None:
                    yield (json.dumps({
                        "type": "error",
                        "message": f"Project not found: {project_id}",
                    }) + "\n").encode("utf-8")
                    return
                digest = build_attention_digest(
                    store, project, trigger=trigger, task_id=task_id
                )
                async for chunk in meta_process_message(
                    project_id,
                    digest,
                    store=store,
                    project=project,
                    origin="supervision",
                    consumed_event_id=event_id,
                ):
                    yield chunk.encode("utf-8")

        return StreamingResponse(
            _stream(),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no"},
        )

    return router
