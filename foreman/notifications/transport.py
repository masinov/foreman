"""How a message is sent: its payload, and the webhook that carries it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from ..domain.models import (
    Event,
    NotificationDelivery,
    NotificationDestination,
    Project,
    Task,
)
from .destinations import DESTINATION_KINDS, WEBHOOK, NotificationError
from .policy import ATTENTION, HUMAN_GATE, TASK_COMPLETED

_LOGGER = logging.getLogger("foreman.notifications")

#: How long a single webhook POST may take. Short on purpose: the worker runs
#: between engine passes, and a destination that hangs should become a retry
#: rather than a pause in the service.
DEFAULT_TIMEOUT_SECONDS = 10.0


#: Payload contract version, bumped when a field changes meaning. Receivers
#: should branch on it rather than on the presence of a key.
PAYLOAD_SCHEMA_VERSION = "1.0"


SIGNATURE_HEADER = "X-Foreman-Signature"


EVENT_HEADER = "X-Foreman-Event"


DELIVERY_HEADER = "X-Foreman-Delivery"


class TransportError(RuntimeError):
    """Raised when one delivery attempt failed.

    Every transport failure is this type, so the worker never has to know
    which library a transport is built on to decide that a retry is due.
    """


#: How each kind reads in a one-line notification.
_SUMMARIES: dict[str, str] = {
    ATTENTION: "Foreman needs attention",
    HUMAN_GATE: "Foreman is waiting for a decision",
    TASK_COMPLETED: "Foreman finished a task",
}


def build_payload(
    *,
    kind: str,
    event: Event,
    project: Project,
    task: Task | None,
) -> dict[str, Any]:
    """Build the JSON body one notification delivers.

    Deliberately self-contained: a receiver should be able to route and
    display the message without calling back into Foreman, because the most
    likely receiver is a chat webhook that cannot call anything. The event
    payload rides along whole under ``event.payload`` for receivers that do
    want the detail.
    """

    subject = task.title if task is not None else project.name
    body: dict[str, Any] = {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "kind": kind,
        "summary": f"{_SUMMARIES.get(kind, 'Foreman event')}: {subject}",
        "occurred_at": event.timestamp,
        "project": {"id": project.id, "name": project.name},
        "event": {
            "id": event.id,
            "type": event.event_type,
            "run_id": event.run_id or None,
            "payload": dict(event.payload or {}),
        },
        "task": None,
    }
    if task is not None:
        body["task"] = {
            "id": task.id,
            "key": getattr(task, "task_key", None),
            "title": task.title,
            "status": task.status,
            "task_type": task.task_type,
            "branch": task.branch_name,
        }
    return body


class NotificationTransport(Protocol):
    """How a delivery reaches one destination.

    One method, and one failure type: implementations raise
    :class:`TransportError` for anything the worker should retry, and return
    a short human-readable detail on success.
    """

    def send(
        self, destination: NotificationDestination, delivery: NotificationDelivery
    ) -> str: ...


@dataclass(slots=True)
class WebhookTransport:
    """POST the delivery payload as JSON to the destination's URL.

    Any response outside 2xx is a failure, as is any network error: the caller
    asked for the message to arrive, and a 500 means it did not. When the
    destination names ``secret_env``, the request carries an HMAC-SHA256 of
    the exact bytes sent, so a receiver can tell a real Foreman from anyone
    who learned the URL.
    """

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    #: Injected so tests exercise this class rather than a stand-in for it.
    opener: Callable[..., Any] = urllib.request.urlopen
    environ: Mapping[str, str] | None = None

    def send(
        self, destination: NotificationDestination, delivery: NotificationDelivery
    ) -> str:
        url = (destination.target or "").strip()
        if not url:
            raise TransportError("Destination has no URL.")
        body = json.dumps(delivery.payload, sort_keys=True).encode("utf-8")
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header(EVENT_HEADER, delivery.kind)
        request.add_header(DELIVERY_HEADER, delivery.id)
        for header, value in _config_headers(destination).items():
            request.add_header(header, value)
        signature = self._signature(destination, body)
        if signature is not None:
            request.add_header(SIGNATURE_HEADER, signature)

        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                status = int(getattr(response, "status", 0) or 0)
        except urllib.error.HTTPError as exc:
            raise TransportError(f"HTTP {exc.code} from {url}") from exc
        except urllib.error.URLError as exc:
            raise TransportError(f"Could not reach {url}: {exc.reason}") from exc
        except OSError as exc:
            raise TransportError(f"Could not reach {url}: {exc}") from exc
        if not 200 <= status < 300:
            raise TransportError(f"HTTP {status} from {url}")
        return f"HTTP {status}"

    def _signature(
        self, destination: NotificationDestination, body: bytes
    ) -> str | None:
        """Return the ``sha256=`` signature header value, when configured."""

        name = str((destination.config or {}).get("secret_env") or "").strip()
        if not name:
            return None
        environ = self.environ if self.environ is not None else os.environ
        secret = environ.get(name)
        if not secret:
            # A named-but-missing variable is a misconfiguration, not a reason
            # to drop the message: send it unsigned and say so in the log.
            _LOGGER.warning(
                "notification destination %s names secret_env %s, which is unset",
                destination.id,
                name,
            )
            return None
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"


def _config_headers(destination: NotificationDestination) -> dict[str, str]:
    """Return the destination's extra request headers, ignoring malformed ones."""

    headers = (destination.config or {}).get("headers")
    if not isinstance(headers, Mapping):
        return {}
    return {
        str(name): str(value)
        for name, value in headers.items()
        if isinstance(name, str) and name.strip()
    }


def build_transport(destination: NotificationDestination) -> NotificationTransport:
    """Return the transport that serves one destination's kind."""

    if destination.kind == WEBHOOK:
        return WebhookTransport()
    raise NotificationError(
        f"Unknown notification destination kind: {destination.kind}. "
        f"Expected one of: {', '.join(DESTINATION_KINDS)}."
    )
