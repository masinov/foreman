"""A user's holds on work (ADR-0043): Pause, Stop and Resume on a task, a
sprint or the workspace; Block and Unblock of a sprint or the workspace.

A task's own Block and Unblock stay under ``/tasks/{id}/block``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..context import ApiContext
from ..schemas import HoldBlock, HoldPause, RequestedBy, body_as


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    # ── A task ───────────────────────────────────────────────────────────

    @router.post("/tasks/{task_id}/pause")
    def pause_task(task_id: str, body: HoldPause = Depends(body_as(HoldPause))) -> dict[str, Any]:
        return with_api(
            lambda api: api.holds.pause_task(
                task_id, mode=body.mode, requested_by=body.requested_by
            )
        )

    @router.post("/tasks/{task_id}/stop")
    def stop_task(task_id: str, body: RequestedBy = Depends(body_as(RequestedBy))) -> dict[str, Any]:
        return with_api(lambda api: api.holds.stop_task(task_id, requested_by=body.requested_by))

    @router.post("/tasks/{task_id}/resume")
    def resume_task(
        task_id: str, body: RequestedBy = Depends(body_as(RequestedBy))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.holds.resume_task(task_id, requested_by=body.requested_by)
        )

    # ── A sprint ─────────────────────────────────────────────────────────

    @router.post("/sprints/{sprint_id}/pause")
    def pause_sprint(
        sprint_id: str, body: HoldPause = Depends(body_as(HoldPause))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.holds.pause_sprint(
                sprint_id, mode=body.mode, requested_by=body.requested_by
            )
        )

    @router.post("/sprints/{sprint_id}/stop")
    def stop_sprint(
        sprint_id: str, body: RequestedBy = Depends(body_as(RequestedBy))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.holds.pause_sprint(
                sprint_id, mode="now", requested_by=body.requested_by
            )
        )

    @router.post("/sprints/{sprint_id}/resume")
    def resume_sprint(
        sprint_id: str, body: RequestedBy = Depends(body_as(RequestedBy))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.holds.resume_sprint(sprint_id, requested_by=body.requested_by)
        )

    @router.post("/sprints/{sprint_id}/block")
    def block_sprint(
        sprint_id: str, body: HoldBlock = Depends(body_as(HoldBlock))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.holds.block_sprint(
                sprint_id, reason=body.reason, requested_by=body.requested_by
            )
        )

    @router.post("/sprints/{sprint_id}/unblock")
    def unblock_sprint(
        sprint_id: str, body: RequestedBy = Depends(body_as(RequestedBy))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.holds.unblock_sprint(sprint_id, requested_by=body.requested_by)
        )

    # ── The workspace ────────────────────────────────────────────────────

    @router.post("/workspace/pause")
    def pause_all(body: HoldPause = Depends(body_as(HoldPause))) -> dict[str, Any]:
        return with_api(
            lambda api: api.holds.pause_all(mode=body.mode, requested_by=body.requested_by)
        )

    @router.post("/workspace/stop")
    def stop_all(body: RequestedBy = Depends(body_as(RequestedBy))) -> dict[str, Any]:
        return with_api(
            lambda api: api.holds.pause_all(mode="now", requested_by=body.requested_by)
        )

    @router.post("/workspace/resume")
    def resume_all(body: RequestedBy = Depends(body_as(RequestedBy))) -> dict[str, Any]:
        return with_api(lambda api: api.holds.resume_all(requested_by=body.requested_by))

    @router.post("/workspace/block")
    def block_all(body: HoldBlock = Depends(body_as(HoldBlock))) -> dict[str, Any]:
        return with_api(
            lambda api: api.holds.block_all(reason=body.reason, requested_by=body.requested_by)
        )

    @router.post("/workspace/unblock")
    def unblock_all(body: RequestedBy = Depends(body_as(RequestedBy))) -> dict[str, Any]:
        return with_api(lambda api: api.holds.unblock_all(requested_by=body.requested_by))

    return router
