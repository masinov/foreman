"""FastAPI backend for the Foreman dashboard."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

from .dashboard import (
    DASHBOARD_ASSETS_DIR,
    DASHBOARD_INDEX_PATH,
    ensure_dashboard_assets,
)
from .dashboard_api import (
    ACTIVITY_EVENT_LIMIT,
    STREAM_BATCH_LIMIT,
    STREAM_HEARTBEAT_SECONDS,
    STREAM_POLL_INTERVAL_SECONDS,
    DashboardAPI,
    DashboardActionError,
    DashboardNotFoundError,
    DashboardValidationError,
)
from .store import ForemanStore


@contextmanager
def _open_store(db_path: str) -> Iterator[ForemanStore]:
    store = ForemanStore(db_path)
    store.initialize()
    try:
        yield store
    finally:
        store.close()


def _encode_sse_message(
    payload: dict[str, Any],
    *,
    event_id: str | None = None,
    event_name: str | None = None,
) -> bytes:
    chunks: list[str] = []
    if event_id:
        chunks.append(f"id: {event_id}")
    if event_name:
        chunks.append(f"event: {event_name}")
    for line in json.dumps(payload).splitlines():
        chunks.append(f"data: {line}")
    chunks.append("")
    chunks.append("")
    return "\n".join(chunks).encode("utf-8")


async def _read_json_body(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body:
        return {}
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DashboardValidationError("Invalid JSON") from exc
    if not isinstance(data, dict):
        raise DashboardValidationError("JSON object required")
    return data


def create_dashboard_app(db_path: str) -> FastAPI:
    """Create the FastAPI application used for dashboard delivery."""

    ensure_dashboard_assets()

    app = FastAPI(
        title="Foreman Dashboard API",
        version="0.1.0",
    )
    app.state.db_path = db_path
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DashboardNotFoundError)
    async def handle_not_found(_: Request, exc: DashboardNotFoundError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=404)

    @app.exception_handler(DashboardValidationError)
    async def handle_validation(_: Request, exc: DashboardValidationError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(DashboardActionError)
    async def handle_action(_: Request, exc: DashboardActionError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=500)

    def with_api(callback):
        with _open_store(db_path) as store:
            return callback(DashboardAPI(store))

    dashboard_html = DASHBOARD_INDEX_PATH.read_text(encoding="utf-8")

    def _resolve_asset_path(asset_path: str) -> Path | None:
        candidate = (DASHBOARD_ASSETS_DIR / asset_path).resolve()
        try:
            candidate.relative_to(DASHBOARD_ASSETS_DIR.resolve())
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    @app.get("/", include_in_schema=False)
    async def dashboard_root() -> RedirectResponse:
        return RedirectResponse(url="/dashboard")

    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    async def dashboard_asset(asset_path: str) -> Response:
        asset_file = _resolve_asset_path(asset_path)
        if asset_file is None:
            return Response(status_code=404)
        media_type = mimetypes.guess_type(asset_file.name)[0] or "application/octet-stream"
        return Response(asset_file.read_bytes(), media_type=media_type)

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/dashboard/{path:path}", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard_shell(path: str = "") -> HTMLResponse:
        return HTMLResponse(dashboard_html)

    @app.get("/api/projects")
    async def list_projects() -> dict[str, Any]:
        return with_api(lambda api: api.list_projects())

    @app.get("/api/projects/{project_id}")
    async def get_project(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_project(project_id))

    @app.get("/api/projects/{project_id}/sprints")
    async def list_project_sprints(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.list_project_sprints(project_id))

    @app.get("/api/sprints/{sprint_id}")
    async def get_sprint(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_sprint(sprint_id))

    @app.get("/api/sprints/{sprint_id}/tasks")
    async def list_sprint_tasks(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.list_sprint_tasks(sprint_id))

    @app.get("/api/sprints/{sprint_id}/events")
    async def list_sprint_events(
        sprint_id: str,
        limit: str = str(ACTIVITY_EVENT_LIMIT),
        after: str | None = None,
    ) -> dict[str, Any]:
        try:
            parsed_limit = int(limit)
        except ValueError as exc:
            raise DashboardValidationError("Invalid limit") from exc
        return with_api(
            lambda api: api.list_sprint_events(
                sprint_id,
                limit=parsed_limit,
                after_event_id=after,
            )
        )

    @app.get("/api/sprints/{sprint_id}/stream")
    async def stream_sprint_events(
        sprint_id: str,
        request: Request,
        after: str | None = None,
    ) -> StreamingResponse:
        with_api(lambda api: api.get_sprint(sprint_id))

        async def event_stream():
            last_event_id = request.headers.get("Last-Event-ID") or after
            last_heartbeat_at = time.monotonic()
            yield b"retry: 1000\n\n"

            with _open_store(db_path) as store:
                api = DashboardAPI(store)
                while True:
                    if await request.is_disconnected():
                        break

                    messages = api.list_sprint_stream_messages(
                        sprint_id,
                        limit=STREAM_BATCH_LIMIT,
                        after_event_id=last_event_id,
                    )
                    if messages:
                        for message in messages:
                            last_event_id = str(message["event_id"])
                            yield _encode_sse_message(
                                message["payload"],
                                event_id=last_event_id,
                            )
                        last_heartbeat_at = time.monotonic()
                    elif time.monotonic() - last_heartbeat_at >= STREAM_HEARTBEAT_SECONDS:
                        yield b": keepalive\n\n"
                        last_heartbeat_at = time.monotonic()

                    await asyncio.sleep(STREAM_POLL_INTERVAL_SECONDS)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_task(task_id))

    @app.post("/api/tasks/{task_id}/approve")
    async def approve_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.approve_task(task_id))

    @app.post("/api/tasks/{task_id}/deny")
    async def deny_task(task_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        return with_api(lambda api: api.deny_task(task_id, note=data.get("note")))

    @app.post("/api/tasks/{task_id}/messages")
    async def create_human_message(task_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        return with_api(
            lambda api: api.create_human_message(task_id, text=str(data.get("text", "")))
        )

    return app
