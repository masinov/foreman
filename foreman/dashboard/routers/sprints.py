"""Sprints, their tasks, their events and the live event stream."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ...dashboard_service import (
    ACTIVITY_EVENT_LIMIT,
    STREAM_BATCH_LIMIT,
    STREAM_HEARTBEAT_SECONDS,
    STREAM_POLL_INTERVAL_SECONDS,
    DashboardService,
    DashboardValidationError,
)
from ..context import (
    MAX_EVENTS_PAGE_LIMIT,
    ApiContext,
    encode_sse_message,
    open_store,
    read_json_body,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/projects/{project_id}/sprints")
    async def list_project_sprints(project_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.list_project_sprints(project_id))

    @router.post("/projects/{project_id}/sprints")
    async def create_sprint(project_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
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

    @router.get("/sprints/{sprint_id}")
    async def get_sprint(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_sprint(sprint_id))

    @router.get("/sprints/{sprint_id}/tasks")
    async def list_sprint_tasks(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.list_sprint_tasks(sprint_id))

    @router.post("/sprints/{sprint_id}/tasks")
    async def create_task(sprint_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        depends_on = data.get("depends_on")
        if depends_on is not None and not isinstance(depends_on, list):
            raise DashboardValidationError("'depends_on' must be a list of task ids.")
        return with_api(
            lambda api: api.create_task(
                sprint_id,
                title=str(data.get("title", "")),
                task_type=str(data.get("task_type", "feature")),
                acceptance_criteria=data.get("acceptance_criteria"),
                description=data.get("description"),
                complexity=data.get("complexity") or None,
                depends_on=depends_on,
            )
        )

    @router.get("/sprints/{sprint_id}/events")
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
        if parsed_limit < 1:
            raise DashboardValidationError("Invalid limit")
        parsed_limit = min(parsed_limit, MAX_EVENTS_PAGE_LIMIT)
        return with_api(
            lambda api: api.list_sprint_events(
                sprint_id,
                limit=parsed_limit,
                after_event_id=after,
                before_event_id=before,
            )
        )

    @router.get("/sprints/{sprint_id}/stream")
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

            with open_store(ctx.db_path) as store:
                api = DashboardService(store)
                # Track SQLite's data_version so we only run the (relatively)
                # expensive sprint-events query when another connection (the
                # engine) has actually committed since the last tick.
                last_data_version: int | None = None
                while True:
                    if await request.is_disconnected():
                        break

                    data_version = store.data_version()
                    if data_version == last_data_version:
                        if time.monotonic() - last_heartbeat_at >= STREAM_HEARTBEAT_SECONDS:
                            yield b": keepalive\n\n"
                            last_heartbeat_at = time.monotonic()
                        await asyncio.sleep(STREAM_POLL_INTERVAL_SECONDS)
                        continue
                    last_data_version = data_version

                    messages = api.list_sprint_stream_messages(
                        sprint_id,
                        limit=STREAM_BATCH_LIMIT,
                        after_event_id=last_event_id,
                    )
                    if messages:
                        for message in messages:
                            last_event_id = str(message["event_id"])
                            yield encode_sse_message(
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

    @router.delete("/sprints/{sprint_id}")
    async def delete_sprint(sprint_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.delete_sprint(sprint_id))

    @router.patch("/sprints/{sprint_id}")
    async def patch_sprint(sprint_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        if "status" in data:
            target_status = data["status"]
            return with_api(
                lambda api: api.transition_sprint(sprint_id, target_status=str(target_status))
            )
        field_updates = {k: v for k, v in data.items()}
        return with_api(lambda api: api.update_sprint_fields(sprint_id, updates=field_updates))

    return router
