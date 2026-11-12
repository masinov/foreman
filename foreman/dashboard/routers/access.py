"""Workspace settings: the session, this machine, runners, API tokens and notification channels."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from ... import dashboard_access as access
from ..context import ApiContext
from ..schemas import ChannelCreate, TokenCreate, body_as


def build_router(ctx: ApiContext) -> APIRouter:
    """Return the routes for this resource, bound to one dashboard's context."""

    router = APIRouter()
    with_store = ctx.with_store

    @router.get("/session")
    def get_session() -> dict[str, Any]:
        return access.describe_session(auth_required=ctx.auth_required)

    @router.get("/machine")
    def get_machine(request: Request) -> dict[str, Any]:
        # The address is the one this request used, so it is what a person
        # would type to come back.
        return access.describe_machine(
            db_path=ctx.db_path, address=str(request.base_url)
        )

    @router.get("/runners")
    def get_runners() -> dict[str, Any]:
        return access.describe_runner_backends()

    @router.get("/tokens")
    def list_tokens() -> dict[str, Any]:
        return with_store(access.list_tokens)

    @router.post("/projects/{project_id}/tokens")
    def create_token(project_id: str, body: TokenCreate = Depends(body_as(TokenCreate))) -> dict[str, Any]:
        return with_store(
            lambda store: access.create_token(store, project_id, name=body.name, scopes=body.scopes)
        )

    @router.post("/tokens/{token_id}/revoke")
    def revoke_token(token_id: str) -> dict[str, Any]:
        return with_store(lambda store: access.revoke_token(store, token_id))

    @router.get("/notification-channels")
    def list_channels() -> dict[str, Any]:
        return with_store(access.list_channels)

    @router.post("/projects/{project_id}/notification-channels")
    def create_channel(
        project_id: str, body: ChannelCreate = Depends(body_as(ChannelCreate))
    ) -> dict[str, Any]:
        return with_store(
            lambda store: access.create_channel(
                store,
                project_id,
                name=body.name,
                url=body.url,
                kind=body.kind,
                secret_env=body.secret_env,
            )
        )

    @router.delete("/notification-channels/{channel_id}")
    def delete_channel(channel_id: str) -> dict[str, Any]:
        return with_store(lambda store: access.delete_channel(store, channel_id))

    return router
