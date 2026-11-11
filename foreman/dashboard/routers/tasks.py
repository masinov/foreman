"""Tasks and the decisions a person takes on them."""

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

    @router.get("/tasks/{task_id}")
    async def get_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_task(task_id))

    @router.delete("/tasks/{task_id}")
    async def delete_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.delete_task(task_id))

    @router.patch("/tasks/{task_id}")
    async def update_task(task_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        return with_api(lambda api: api.update_task_fields(task_id, updates=data))

    @router.post("/tasks/{task_id}/stop")
    async def stop_task(task_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        requested_by = data.get("requested_by") or None
        return with_api(lambda api: api.stop_task(task_id, requested_by=requested_by))

    @router.post("/tasks/{task_id}/accept")
    async def accept_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.accept_task(task_id))

    @router.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.cancel_task(task_id))

    @router.post("/tasks/{task_id}/approve")
    async def approve_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.approve_task(task_id))

    @router.post("/tasks/{task_id}/deny")
    async def deny_task(task_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        return with_api(lambda api: api.deny_task(task_id, note=data.get("note")))

    @router.post("/tasks/{task_id}/messages")
    async def create_human_message(task_id: str, request: Request) -> dict[str, Any]:
        data = await read_json_body(request)
        return with_api(
            lambda api: api.create_human_message(task_id, text=str(data.get("text", "")))
        )

    return router
