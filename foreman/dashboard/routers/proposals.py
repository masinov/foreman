"""Proposals: changes the manager proposes and a person confirms (ADR-0022)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ...proposals import PROPOSAL_PAGE_LIMIT
from ..context import MAX_PAGE_LIMIT, ApiContext, split_values
from ..schemas import RequestedBy, body_as


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_api = ctx.with_api

    @router.get("/projects/{project_id}/proposals")
    def list_proposals(
        project_id: str,
        state: list[str] = Query(default=[]),
        limit: int = Query(default=PROPOSAL_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        states = split_values(state)
        return with_api(
            lambda api: api.list_proposals(project_id, states=states, limit=limit, offset=offset)
        )

    @router.get("/proposals/{proposal_id}")
    def get_proposal(proposal_id: str) -> dict[str, Any]:
        return with_api(lambda api: api.get_proposal(proposal_id))

    @router.post("/proposals/{proposal_id}/confirm")
    def confirm_proposal(
        proposal_id: str, body: RequestedBy = Depends(body_as(RequestedBy))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.confirm_proposal(proposal_id, requested_by=body.requested_by)
        )

    @router.post("/proposals/{proposal_id}/decline")
    def decline_proposal(
        proposal_id: str, body: RequestedBy = Depends(body_as(RequestedBy))
    ) -> dict[str, Any]:
        return with_api(
            lambda api: api.decline_proposal(proposal_id, requested_by=body.requested_by)
        )

    return router
