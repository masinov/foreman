"""FastAPI backend for the Foreman dashboard."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

from .dashboard_runtime import (
    DASHBOARD_ASSETS_DIR,
    DASHBOARD_INDEX_PATH,
    build_frontend_dev_redirect_url,
    ensure_dashboard_assets,
    normalize_frontend_dev_url,
)
from .dashboard_service import (
    ACTIVITY_EVENT_LIMIT,
    STREAM_BATCH_LIMIT,
    STREAM_HEARTBEAT_SECONDS,
    STREAM_POLL_INTERVAL_SECONDS,
    DashboardService,
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


def create_dashboard_app(
    db_path: str,
    *,
    frontend_mode: str = "dist",
    frontend_dev_url: str | None = None,
) -> FastAPI:
    """Create the FastAPI application used for dashboard delivery."""

    if frontend_mode == "dist":
        ensure_dashboard_assets()
    elif frontend_mode == "dev":
        if frontend_dev_url is None:
            raise RuntimeError("Frontend dev mode requires a frontend dev URL.")
        frontend_dev_url = normalize_frontend_dev_url(frontend_dev_url)
    else:
        raise RuntimeError(
            f"Unsupported dashboard frontend mode: {frontend_mode}. Expected `dist` or `dev`."
        )

    app = FastAPI(
        title="Foreman Dashboard API",
        version="0.1.0",
    )
    app.state.db_path = db_path
    app.state.frontend_mode = frontend_mode
    app.state.frontend_dev_url = frontend_dev_url
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
            return callback(DashboardService(store))

    dashboard_html = (
        DASHBOARD_INDEX_PATH.read_text(encoding="utf-8")
        if frontend_mode == "dist"
        else None
    )

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
        if frontend_mode == "dev":
            return RedirectResponse(
                url=build_frontend_dev_redirect_url(frontend_dev_url, "/dashboard")
            )
        return RedirectResponse(url="/dashboard")

    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    async def dashboard_asset(asset_path: str) -> Response:
        if frontend_mode != "dist":
            return Response(status_code=404)
        asset_file = _resolve_asset_path(asset_path)
        if asset_file is None:
            return Response(status_code=404)
        media_type = mimetypes.guess_type(asset_file.name)[0] or "application/octet-stream"
        return Response(asset_file.read_bytes(), media_type=media_type)

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/dashboard/{path:path}", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard_shell(path: str = "") -> Response:
        if frontend_mode == "dev":
            route_path = "/dashboard"
            if path:
                route_path = f"{route_path}/{path}"
            return RedirectResponse(
                url=build_frontend_dev_redirect_url(frontend_dev_url, route_path)
            )
        return HTMLResponse(dashboard_html)

    @app.get("/api/projects")
    async def list_projects() -> dict[str, Any]:
        return with_api(lambda api: api.list_projects())

    @app.post("/api/projects")
    async def create_project(request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        return with_api(
            lambda api: api.create_project(
                name=str(data.get("name", "")),
                repo_path=str(data.get("repo_path", "")),
                workflow_id=str(data.get("workflow_id", "development")),
            )
        )

    @app.get("/api/projects/{project_id}")
    async def get_project(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_project(project_id))

    @app.get("/api/projects/{project_id}/settings")
    async def get_project_settings(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_project_settings(project_id))

    @app.patch("/api/projects/{project_id}/settings")
    async def update_project_settings(project_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        return with_api(
            lambda api: api.update_project_settings(project_id, updates=data)
        )

    @app.get("/api/projects/{project_id}/sprints")
    async def list_project_sprints(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.list_project_sprints(project_id))

    @app.post("/api/projects/{project_id}/sprints")
    async def create_sprint(project_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        initial_tasks = data.get("initial_tasks")
        if initial_tasks is not None and not isinstance(initial_tasks, list):
            raise DashboardValidationError("'initial_tasks' must be a list.")
        return with_api(
            lambda api: api.create_sprint(
                project_id,
                title=str(data.get("title", "")),
                goal=data.get("goal"),
                initial_tasks=initial_tasks,
            )
        )

    @app.get("/api/sprints/{sprint_id}")
    async def get_sprint(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_sprint(sprint_id))

    @app.get("/api/sprints/{sprint_id}/tasks")
    async def list_sprint_tasks(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.list_sprint_tasks(sprint_id))

    @app.post("/api/sprints/{sprint_id}/tasks")
    async def create_task(sprint_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        return with_api(
            lambda api: api.create_task(
                sprint_id,
                title=str(data.get("title", "")),
                task_type=str(data.get("task_type", "feature")),
                acceptance_criteria=data.get("acceptance_criteria"),
            )
        )

    @app.get("/api/sprints/{sprint_id}/events")
    async def list_sprint_events(
        sprint_id: str,
        limit: str = str(ACTIVITY_EVENT_LIMIT),
        after: str | None = None,
        before: str | None = None,
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
                before_event_id=before,
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
                api = DashboardService(store)
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

    @app.delete("/api/sprints/{sprint_id}")
    async def delete_sprint(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.delete_sprint(sprint_id))

    @app.patch("/api/sprints/{sprint_id}")
    async def patch_sprint(sprint_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        if "status" in data:
            target_status = data["status"]
            return with_api(
                lambda api: api.transition_sprint(sprint_id, target_status=str(target_status))
            )
        field_updates = {k: v for k, v in data.items()}
        return with_api(lambda api: api.update_sprint_fields(sprint_id, updates=field_updates))

    @app.post("/api/projects/{project_id}/meta/message")
    async def meta_message(project_id: str, request: Request) -> StreamingResponse:
        from .meta_agent import process_message as meta_process_message

        data = await _read_json_body(request)
        message = str(data.get("message", "")).strip()
        if not message:
            raise DashboardValidationError("message cannot be empty.")

        with _open_store(db_path) as store:
            project = store.get_project(project_id)
            if project is None:
                raise DashboardNotFoundError(f"Project not found: {project_id}")
            sprints_payload = DashboardService(store).list_project_sprints(project_id)

        sprints = sprints_payload.get("sprints", [])

        async def _stream():
            async for chunk in meta_process_message(
                project_id,
                message,
                project=project,
                sprints=sprints,
            ):
                yield chunk.encode("utf-8")

        return StreamingResponse(
            _stream(),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no"},
        )

    @app.get("/api/projects/{project_id}/meta/history")
    async def meta_history(project_id: str) -> dict[str, Any]:
        from .meta_agent import get_history as meta_get_history

        with _open_store(db_path) as store:
            project = store.get_project(project_id)
            if project is None:
                raise DashboardNotFoundError(f"Project not found: {project_id}")
        turns = meta_get_history(project_id)
        return {"project_id": project_id, "turns": turns}

    @app.delete("/api/projects/{project_id}/meta/session")
    async def clear_meta_session(project_id: str) -> dict[str, Any]:
        from .meta_agent import clear_session as meta_clear_session

        with _open_store(db_path) as store:
            project = store.get_project(project_id)
            if project is None:
                raise DashboardNotFoundError(f"Project not found: {project_id}")
        meta_clear_session(project_id)
        return {"project_id": project_id, "cleared": True}

    @app.post("/api/projects/{project_id}/gates")
    async def create_gate(project_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        return with_api(lambda api: api.create_gate(
            project_id,
            sprint_id=str(data.get("sprint_id", "")),
            conflict_description=str(data.get("conflict_description", "")),
            suggested_order=data.get("suggested_order") or [],
            suggested_reason=str(data.get("suggested_reason", "")),
        ))

    @app.get("/api/projects/{project_id}/gates")
    async def list_gates(project_id: str, status: str | None = None) -> dict[str, Any]:
        return with_api(lambda api: api.list_gates(project_id, status=status))

    @app.patch("/api/gates/{gate_id}")
    async def resolve_gate(gate_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        resolution = str(data.get("resolution", ""))
        resolved_by = str(data.get("resolved_by", "human"))
        return with_api(lambda api: api.resolve_gate(gate_id, resolution=resolution, resolved_by=resolved_by))

    @app.post("/api/projects/{project_id}/agent/stop")
    async def stop_agent(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.stop_agent(project_id))

    @app.post("/api/projects/{project_id}/agent/start")
    async def start_agent(project_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        task_id = data.get("task_id") or None
        return with_api(lambda api: api.start_agent(project_id, task_id=task_id))

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_task(task_id))

    @app.delete("/api/tasks/{task_id}")
    async def delete_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.delete_task(task_id))

    @app.patch("/api/tasks/{task_id}")
    async def update_task(task_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        return with_api(lambda api: api.update_task_fields(task_id, updates=data))

    @app.post("/api/tasks/{task_id}/stop")
    async def stop_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.stop_task(task_id))

    @app.post("/api/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.cancel_task(task_id))

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

    @app.get("/api/roles")
    async def list_roles() -> dict[str, Any]:
        return with_api(lambda api: api.list_roles())

    @app.patch("/api/roles/{role_id}")
    async def update_role(role_id: str, request: Request) -> dict[str, Any]:
        data = await _read_json_body(request)
        return with_api(lambda api: api.update_role(role_id, updates=data))

    return app


def create_dashboard_app_from_env() -> FastAPI:
    """Create the dashboard app from environment for uvicorn reload mode."""

    db_path = os.environ.get("FOREMAN_DASHBOARD_DB_PATH")
    if not db_path:
        raise RuntimeError("FOREMAN_DASHBOARD_DB_PATH is required for dashboard reload mode.")

    frontend_mode = os.environ.get("FOREMAN_DASHBOARD_FRONTEND_MODE", "dist")
    frontend_dev_url = os.environ.get("FOREMAN_DASHBOARD_FRONTEND_DEV_URL")
    return create_dashboard_app(
        db_path,
        frontend_mode=frontend_mode,
        frontend_dev_url=frontend_dev_url,
    )
