"""Tasks and the decisions a person takes on them."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..schemas import GuidanceNote, RequestedBy, TaskDenial, body_as
from ..context import (
    ApiContext,
    read_json_body,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_task(task_id))

    @router.delete("/tasks/{task_id}")
    def delete_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.delete_task(task_id))

    @router.patch("/tasks/{task_id}")
    def update_task(task_id: str, data: dict[str, Any] = Depends(read_json_body)) -> dict[str, Any]:
        return with_api(lambda api: api.update_task_fields(task_id, updates=data))

    @router.post("/tasks/{task_id}/stop")
    def stop_task(
        task_id: str, body: RequestedBy = Depends(body_as(RequestedBy))
    ) -> dict[str, Any]:
        requested_by = body.requested_by or None
        return with_api(lambda api: api.stop_task(task_id, requested_by=requested_by))

    @router.post("/tasks/{task_id}/accept")
    def accept_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.accept_task(task_id))

    @router.post("/tasks/{task_id}/cancel")
    def cancel_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.cancel_task(task_id))

    @router.post("/tasks/{task_id}/approve")
    def approve_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.approve_task(task_id))

    @router.post("/tasks/{task_id}/deny")
    def deny_task(
        task_id: str, body: TaskDenial = Depends(body_as(TaskDenial))
    ) -> dict[str, Any]:
        return with_api(lambda api: api.deny_task(task_id, note=body.note))

    @router.post("/tasks/{task_id}/messages")
    def create_human_message(
        task_id: str, body: GuidanceNote = Depends(body_as(GuidanceNote))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.create_human_message(task_id, text=body.text)
        )

    return router
