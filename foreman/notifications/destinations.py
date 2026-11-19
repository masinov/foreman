"""Where messages go: a project's destinations, checked before they are saved.
"""

from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from ..domain.models import NotificationDestination
from ..store import ForemanStore

#: The transport kinds a destination may name.
WEBHOOK = "webhook"


DESTINATION_KINDS: tuple[str, ...] = (WEBHOOK,)


class NotificationError(ValueError):
    """Raised when a destination is malformed."""


def validate_destination_kind(kind: str | None) -> str:
    """Validate a destination kind, defaulting to ``webhook``."""

    value = (kind or WEBHOOK).strip().lower()
    if value not in DESTINATION_KINDS:
        raise NotificationError(
            f"Unknown notification destination kind: {value}. "
            f"Expected one of: {', '.join(DESTINATION_KINDS)}."
        )
    return value


def validate_target(kind: str, target: str | None) -> str:
    """Validate a destination's address for its kind."""

    value = (target or "").strip()
    if kind == WEBHOOK:
        if not value.startswith(("http://", "https://")):
            raise NotificationError(
                "A webhook destination needs an http:// or https:// URL, "
                f"got {value!r}."
            )
    if not value:
        raise NotificationError("A notification destination needs a target.")
    return value


def validate_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate the per-kind options object stored with a destination."""

    if config is None:
        return {}
    if not isinstance(config, Mapping):
        raise NotificationError("Destination config must be a JSON object.")
    cleaned: dict[str, Any] = {}
    headers = config.get("headers")
    if headers is not None:
        if not isinstance(headers, Mapping):
            raise NotificationError("Destination config headers must be an object.")
        # An empty header set is the absence of one; storing `{}` would make
        # every destination created without `--header` carry a stub object.
        if headers:
            cleaned["headers"] = {str(k): str(v) for k, v in headers.items()}
    secret_env = config.get("secret_env")
    if secret_env is not None:
        name = str(secret_env).strip()
        if name:
            cleaned["secret_env"] = name
    return cleaned


def add_destination(
    store: ForemanStore,
    project_id: str,
    *,
    name: str | None,
    url: str | None,
    kind: str | None = None,
    headers: Mapping[str, Any] | None = None,
    secret_env: str | None = None,
) -> NotificationDestination:
    """Validate and save one destination: the one path the CLI and the dashboard share.

    Raises :class:`NotificationError` for a missing name, a name the project
    already uses, or an invalid kind, address or option.
    """

    cleaned_name = (name or "").strip()
    if not cleaned_name:
        raise NotificationError("A notification destination needs a name.")
    if store.find_notification_destination(project_id, cleaned_name) is not None:
        raise NotificationError(
            f"Project {project_id} already has a destination named {cleaned_name!r}. "
            "Remove it first, or choose another name."
        )
    resolved_kind = validate_destination_kind(kind)
    target = validate_target(resolved_kind, url)
    config = validate_config({"headers": headers, "secret_env": secret_env})
    return store.save_notification_destination(
        NotificationDestination(
            id=f"dst-{uuid4().hex[:12]}",
            project_id=project_id,
            name=cleaned_name,
            kind=resolved_kind,
            target=target,
            config=config,
        )
    )
