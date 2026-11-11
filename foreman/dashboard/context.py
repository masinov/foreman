"""What a router needs from the dashboard it is mounted on."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import json
from typing import Any, TypeVar

from fastapi import Request

from ..dashboard_guard import is_json_content_type
from ..dashboard_service import DashboardService, DashboardValidationError
from ..store import ForemanStore

_T = TypeVar("_T")

#: Where the API is served. The first is current; the rest are older paths
#: that still answer.
API_PREFIXES: tuple[str, ...] = ("/api/v1", "/api")


@contextmanager
def open_store(db_path: str) -> Iterator[ForemanStore]:
    """Open a short-lived store for one request.

    The schema is initialized once in ``create_dashboard_app``; per-request
    stores only open a connection so requests never race each other through
    the migration runner.
    """

    store = ForemanStore(db_path)
    try:
        yield store
    finally:
        store.close()


def encode_sse_message(
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


async def read_json_body(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body:
        return {}
    if not is_json_content_type(request.headers.get("content-type")):
        # A declared JSON body is what forces a browser to preflight a
        # cross-origin request; see foreman/dashboard_guard.py.
        raise DashboardValidationError("Content-Type must be application/json")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DashboardValidationError("Invalid JSON") from exc
    if not isinstance(data, dict):
        raise DashboardValidationError("JSON object required")
    return data


class DashboardForbiddenError(Exception):
    """Raised when a route is disabled by the dashboard's security policy."""


MAX_EVENTS_PAGE_LIMIT = 500


TOKEN_HEADER = "X-Foreman-Token"


def presented_token(request: Request) -> str | None:
    """Return the token a request presents, from header or query string.

    The header forms serve fetch calls; the ``token`` query parameter exists
    for ``EventSource``, which cannot set headers, so it is honoured on GET
    requests only. A token in a URL reaches logs and history, and no
    state-changing route needs one there.
    """

    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    header_token = request.headers.get(TOKEN_HEADER)
    if header_token:
        return header_token.strip()
    query_token = request.query_params.get("token") if request.method == "GET" else None
    if query_token:
        return query_token.strip()
    return None


@dataclass(frozen=True)
class ApiContext:
    """One dashboard's database and policy, as its routes see them."""

    db_path: str
    manager_enabled: bool

    def with_api(self, callback: Callable[[DashboardService], _T]) -> _T:
        """Run ``callback`` with a service over a store opened for this request."""

        with open_store(self.db_path) as store:
            return callback(DashboardService(store))

    def require_manager(self) -> None:
        """Refuse a manager-chat route when the manager is disabled."""

        if not self.manager_enabled:
            raise DashboardForbiddenError(
                "The manager chat is disabled on non-loopback binds. Bind the dashboard "
                "to localhost or start it with --allow-remote-manager."
            )
