"""Who is acting, who can reach Foreman, and where it tells people (workspace settings).

These are the reads and writes behind the workspace settings page. Each
operation is the one the CLI already has -- ``foreman token`` and
``foreman notify`` -- on the same store methods and validators, so a token or
a channel made in the browser is the same record a terminal makes.

Errors are the dashboard service's, so the API answers them in the one
envelope (ADR-0019).
"""

from __future__ import annotations

import os
from typing import Any

from . import __version__
from .api_tokens import API_TOKEN_SCOPES, ApiTokenError
from .dashboard_service import DashboardNotFoundError, DashboardValidationError
from .models import ApiToken, NotificationDestination
from .notifications import DESTINATION_KINDS, NotificationError, add_destination
from .runner.discovery import describe_runners
from .store import ForemanStore

#: Who acts when nothing authenticates the dashboard.
LOCAL_OPERATOR = "Local operator"

#: A shared dashboard token is one actor, not a person (MANUAL, security
#: section), so it is named for what it is.
DASHBOARD_TOKEN_NAME = "Dashboard token"

#: Recorded as the creator of tokens made from the dashboard.
CREATED_BY = "dashboard"


def describe_session(*, auth_required: bool) -> dict[str, Any]:
    """Who the server says is acting in this session.

    ``can_sign_out`` is true only where it means something: with a dashboard
    token, signing out forgets that token in the browser. With no
    authentication there is nothing to sign out of. No identity provider
    exists in Foreman yet, so ``identity_provider`` is ``None``.
    """

    return {
        "authentication": "token" if auth_required else "none",
        "name": DASHBOARD_TOKEN_NAME if auth_required else LOCAL_OPERATOR,
        "can_sign_out": auth_required,
        "identity_provider": None,
    }


def describe_machine(*, db_path: str, address: str) -> dict[str, Any]:
    """The values of the machine the server runs on."""

    return {
        "database_path": os.path.abspath(db_path),
        "version": __version__,
        "address": address.rstrip("/"),
    }


def describe_runner_backends() -> dict[str, Any]:
    """The agent backends found on this machine and the models roles ask for."""

    from .roles import RoleLoadError, load_roles

    try:
        roles = load_roles()
    except RoleLoadError as exc:
        raise DashboardValidationError(f"The roles could not be loaded: {exc}") from exc
    return {"runners": describe_runners(roles.values())}


# ── API tokens ───────────────────────────────────────────────────────────


def _token_payload(token: ApiToken, project_names: dict[str, str]) -> dict[str, Any]:
    return {
        "id": token.id,
        "project_id": token.project_id,
        "project_name": project_names.get(token.project_id, token.project_id),
        "name": token.name,
        "scopes": list(token.scopes),
        "created_by": token.created_by,
        "created_at": token.created_at,
        "last_used_at": token.last_used_at,
        "revoked_at": token.revoked_at,
        "active": token.is_active,
    }


def list_tokens(store: ForemanStore) -> dict[str, Any]:
    """Every project's API tokens, newest first, secrets never included."""

    projects = store.list_projects()
    names = {project.id: project.name for project in projects}
    tokens = [token for project in projects for token in store.list_api_tokens(project.id)]
    tokens.sort(key=lambda token: (token.created_at, token.id), reverse=True)
    return {
        "tokens": [_token_payload(token, names) for token in tokens],
        "scopes": sorted(API_TOKEN_SCOPES),
    }


def create_token(
    store: ForemanStore, project_id: str, *, name: str, scopes: list[str] | None
) -> dict[str, Any]:
    """Mint a token. The payload's ``secret`` is the only time it is ever shown."""

    project = store.get_project(project_id)
    if project is None:
        raise DashboardNotFoundError(f"Project not found: {project_id}")
    try:
        token, secret = store.create_api_token(
            project_id=project.id, name=name, scopes=scopes or None, created_by=CREATED_BY
        )
    except (ApiTokenError, ValueError) as exc:
        raise DashboardValidationError(str(exc), field="name" if "name" in str(exc) else "scopes") from exc
    return {**_token_payload(token, {project.id: project.name}), "secret": secret}


def revoke_token(store: ForemanStore, token_id: str) -> dict[str, Any]:
    """Revoke a token (a timestamp, not a delete); revoking twice is harmless."""

    existing = store.get_api_token(token_id)
    if existing is None:
        raise DashboardNotFoundError(f"API token not found: {token_id}")
    token = store.revoke_api_token(existing.id)
    project = store.get_project(existing.project_id)
    names = {existing.project_id: project.name} if project else {}
    return _token_payload(token, names)


# ── Notification channels ────────────────────────────────────────────────


def _channel_payload(destination: NotificationDestination, project_names: dict[str, str]) -> dict[str, Any]:
    return {
        "id": destination.id,
        "project_id": destination.project_id,
        "project_name": project_names.get(destination.project_id, destination.project_id),
        "name": destination.name,
        "kind": destination.kind,
        "target": destination.target,
        "signed": bool(destination.config.get("secret_env")),
        "enabled": destination.enabled,
        "created_at": destination.created_at,
    }


def list_channels(store: ForemanStore) -> dict[str, Any]:
    """Every project's notification destinations, oldest first."""

    projects = store.list_projects()
    names = {project.id: project.name for project in projects}
    channels = [
        destination
        for project in projects
        for destination in store.list_notification_destinations(project.id)
    ]
    channels.sort(key=lambda destination: (destination.created_at, destination.id))
    return {
        "channels": [_channel_payload(destination, names) for destination in channels],
        "kinds": list(DESTINATION_KINDS),
    }


def create_channel(
    store: ForemanStore,
    project_id: str,
    *,
    name: str,
    url: str,
    kind: str | None = None,
    secret_env: str | None = None,
) -> dict[str, Any]:
    """Add a destination to a project, on the validation ``foreman notify add`` uses."""

    project = store.get_project(project_id)
    if project is None:
        raise DashboardNotFoundError(f"Project not found: {project_id}")
    try:
        destination = add_destination(
            store, project.id, name=name, url=url, kind=kind, secret_env=secret_env
        )
    except (NotificationError, ValueError) as exc:
        message = str(exc)
        field = "name" if "name" in message.lower() else "url" if "target" in message or "URL" in message else None
        raise DashboardValidationError(message, field=field) from exc
    return _channel_payload(destination, {project.id: project.name})


def delete_channel(store: ForemanStore, channel_id: str) -> dict[str, Any]:
    """Remove a destination and what was queued for it."""

    destination = store.get_notification_destination(channel_id)
    if destination is None:
        raise DashboardNotFoundError(f"Notification channel not found: {channel_id}")
    store.delete_notification_destination(destination.id)
    return {"id": destination.id, "removed": True}
