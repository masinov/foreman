"""Tasks and the decisions a person takes on them."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..schemas import DocumentRestamp, GuidanceNote, RequestedBy, TaskApproval, TaskBlock, TaskDenial, TaskUnblock, body_as
from ...services.task_reads import TaskReads
from ...services.task_models import FileDiff, RunOutput, TaskDocument, TaskDocumentChange, TaskChanges, TaskChecks, TaskRuns
from ..context import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    ApiContext,
    read_json_body,
)


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.tasks.get_task(task_id))

    @router.delete("/tasks/{task_id}")
    def delete_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.tasks.delete_task(task_id))

    @router.patch("/tasks/{task_id}")
    def update_task(task_id: str, data: dict[str, Any] = Depends(read_json_body)) -> dict[str, Any]:
        return with_api(lambda api: api.tasks.update_task_fields(task_id, updates=data))

    @router.post("/tasks/{task_id}/block")
    def block_task(task_id: str, body: TaskBlock = Depends(body_as(TaskBlock))) -> dict[str, Any]:
        return with_api(
            lambda api: api.tasks.block_task(
                task_id, reason=body.reason, requested_by=body.requested_by
            )
        )

    @router.post("/tasks/{task_id}/unblock")
    def unblock_task(
        task_id: str, body: TaskUnblock = Depends(body_as(TaskUnblock))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.tasks.unblock_task(
                task_id,
                note=body.note,
                reset_visits=body.reset_visits,
                requested_by=body.requested_by,
            )
        )

    @router.post("/tasks/{task_id}/complete")
    def complete_task(task_id: str, body: TaskBlock = Depends(body_as(TaskBlock))) -> dict[str, Any]:
        return with_api(
            lambda api: api.tasks.complete_task(
                task_id, reason=body.reason, requested_by=body.requested_by
            )
        )

    @router.post("/tasks/{task_id}/reopen")
    def reopen_task(
        task_id: str, body: RequestedBy = Depends(body_as(RequestedBy))
    ) -> dict[str, Any]:
        requested_by = body.requested_by or None
        return with_api(lambda api: api.tasks.reopen_task(task_id, requested_by=requested_by))

    @router.post("/tasks/{task_id}/accept")
    def accept_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.tasks.accept_task(task_id))

    @router.post("/tasks/{task_id}/cancel")
    def cancel_task(task_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.tasks.cancel_task(task_id))

    @router.post("/tasks/{task_id}/approve")
    def approve_task(
        task_id: str, body: TaskApproval = Depends(body_as(TaskApproval))
    ) -> dict[str, Any]:
        return with_api(lambda api: api.tasks.approve_task(task_id, version=body.version))

    @router.post("/tasks/{task_id}/deny")
    def deny_task(
        task_id: str, body: TaskDenial = Depends(body_as(TaskDenial))
    ) -> dict[str, Any]:
        return with_api(lambda api: api.tasks.deny_task(task_id, note=body.note))

    @router.post("/tasks/{task_id}/messages")
    def create_human_message(
        task_id: str, body: GuidanceNote = Depends(body_as(GuidanceNote))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.tasks.create_human_message(task_id, text=body.text)
        )

    @router.post("/tasks/{task_id}/steer")
    def steer_task(
        task_id: str, body: GuidanceNote = Depends(body_as(GuidanceNote))
    ) -> dict[str, Any]:
        """Record guidance and interrupt the running agent step so it reads it now."""

        return with_api(lambda api: api.engine.steer_task(task_id, text=body.text))

    @router.get("/tasks/{task_id}/changes", response_model=TaskChanges)
    def get_task_changes(task_id: str) -> TaskChanges:
        return ctx.with_store(lambda store: TaskReads(store).get_changes(task_id))

    @router.get("/tasks/{task_id}/changes/diff", response_model=FileDiff)
    def get_task_file_diff(task_id: str, path: str = Query(min_length=1)) -> FileDiff:
        return ctx.with_store(lambda store: TaskReads(store).get_file_diff(task_id, path))

    @router.get("/tasks/{task_id}/documents", response_model=TaskDocument)
    def get_task_document(
        task_id: str, path: str = Query(min_length=1), heading: str | None = Query(default=None)
    ) -> TaskDocument:
        return ctx.with_store(lambda store: TaskReads(store).get_document(task_id, path, heading))

    @router.get("/tasks/{task_id}/documents/diff", response_model=TaskDocumentChange)
    def get_task_document_change(
        task_id: str, path: str = Query(min_length=1), heading: str | None = Query(default=None)
    ) -> TaskDocumentChange:
        return ctx.with_store(lambda store: TaskReads(store).get_document_change(task_id, path, heading))

    @router.post("/tasks/{task_id}/documents/restamp")
    def restamp_task_document(
        task_id: str, body: DocumentRestamp = Depends(body_as(DocumentRestamp))
    ) -> dict[str, Any]:
        """Mark one document the task rests on as read at the default branch's commit now."""

        return with_api(
            lambda api: api.tasks.restamp_document(task_id, path=body.path, heading=body.heading)
        )

    @router.get("/tasks/{task_id}/checks", response_model=TaskChecks)
    def get_task_checks(task_id: str) -> TaskChecks:
        return ctx.with_store(lambda store: TaskReads(store).get_checks(task_id))

    @router.get("/tasks/{task_id}/runs", response_model=TaskRuns)
    def list_task_runs(
        task_id: str,
        limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
        offset: int = Query(default=0, ge=0),
    ) -> TaskRuns:
        return ctx.with_store(
            lambda store: TaskReads(store).list_runs(task_id, limit=limit, offset=offset)
        )

    @router.get("/runs/{run_id}/output", response_model=RunOutput)
    def get_run_output(run_id: str, raw: bool = Query(default=False)) -> RunOutput:
        return ctx.with_store(lambda store: TaskReads(store).get_run_output(run_id, raw=raw))

    return router
