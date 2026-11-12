"""Telling people what the engine did, on the policy they asked for.

An engine that runs unattended is only useful if it can reach the people who
are not attending it. Foreman decides *whether* to speak in the policy matrix,
which resolves a ``notification`` decision per task and stamps it on the events
worth announcing as a ``notify`` field:

``none``
    say nothing,
``attention``
    the moments that want a person -- engine attention turns and human gates,
``all``
    those, plus a task reaching done.

This module is the other half: where a project wants to be told, and how the
message actually gets there. Three pieces, each with one job.

:class:`NotificationDispatcher`
    Reads a persisted event, decides whether it is announceable, and writes a
    ``pending`` delivery row per destination. It runs inside the engine loop,
    so it does exactly one thing that can be slow -- a small indexed insert --
    and it never raises: a broken notification setup must not fail a task that
    otherwise succeeded.
:class:`NotificationDeliveryWorker`
    Drains due deliveries outside task execution, sends each through its
    transport, and either marks it delivered or schedules a retry with an
    exponential backoff. Exhausted retries leave a ``failed`` row carrying the
    last error, which is the only durable answer to "did anyone hear about
    that?".
:class:`WebhookTransport`
    The one transport that needs no credential beyond a URL. Adding chat or
    email means adding a class here and a row kind, not touching the engine.

The queue in the middle is the reason delivery cannot block a run. The engine
writes; something else sends; a destination that is down costs a row and a
retry rather than a stalled pass or a failed task.
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
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol, TYPE_CHECKING
from uuid import uuid4

from .models import Event, NotificationDelivery, NotificationDestination, Project, Task
from .policy import POLICY_DEFAULTS, POLICY_VALUES, PolicyMatrix

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking
    from .store import ForemanStore

_LOGGER = logging.getLogger("foreman.notifications")

#: The values the ``notification`` policy decision may take, quietest first.
NOTIFICATION_POLICIES: tuple[str, ...] = POLICY_VALUES["notification"]

#: Used when nothing resolved a policy. ``attention`` rather than ``none``: a
#: project that configured a destination at all wants the moments that need a
#: person, and silence is the failure mode nobody notices.
DEFAULT_NOTIFICATION_POLICY = POLICY_DEFAULTS["notification"]

#: What a delivery is about.
ATTENTION = "attention"
HUMAN_GATE = "human_gate"
TASK_COMPLETED = "task_completed"

NOTIFICATION_KINDS: tuple[str, ...] = (ATTENTION, HUMAN_GATE, TASK_COMPLETED)

#: Which kinds each policy delivers. ``all`` is ``attention`` plus completions,
#: so the ladder is inclusive rather than three unrelated sets.
_POLICY_KINDS: dict[str, frozenset[str]] = {
    "none": frozenset(),
    "attention": frozenset({ATTENTION, HUMAN_GATE}),
    "all": frozenset({ATTENTION, HUMAN_GATE, TASK_COMPLETED}),
}

#: The persisted event types that can become a notification, and the kind each
#: one carries. ``workflow.paused`` is only announceable when it paused for a
#: person; the quota pause is the engine waiting, not a human gate.
_EVENT_KINDS: dict[str, str] = {
    "engine.attention_needed": ATTENTION,
    "workflow.paused": HUMAN_GATE,
    "task.completed": TASK_COMPLETED,
}

#: The transport kinds a destination may name.
WEBHOOK = "webhook"
DESTINATION_KINDS: tuple[str, ...] = (WEBHOOK,)

#: Retry schedule. Attempt *n* waits ``BASE * 2**(n-1)``, capped, so a
#: destination that is briefly down is caught within a minute and one that is
#: down for an afternoon is not hammered.
RETRY_BASE_SECONDS = 30.0
RETRY_MAX_SECONDS = 1800.0
DEFAULT_MAX_ATTEMPTS = 5

#: How long a single webhook POST may take. Short on purpose: the worker runs
#: between engine passes, and a destination that hangs should become a retry
#: rather than a pause in the service.
DEFAULT_TIMEOUT_SECONDS = 10.0

#: How many deliveries one drain sends before returning to the caller. Bounds
#: the worst case a slow destination can add to a pass.
DEFAULT_DRAIN_LIMIT = 20

#: Payload contract version, bumped when a field changes meaning. Receivers
#: should branch on it rather than on the presence of a key.
PAYLOAD_SCHEMA_VERSION = "1.0"

SIGNATURE_HEADER = "X-Foreman-Signature"
EVENT_HEADER = "X-Foreman-Event"
DELIVERY_HEADER = "X-Foreman-Delivery"


class NotificationError(ValueError):
    """Raised when a destination is malformed."""


class TransportError(RuntimeError):
    """Raised when one delivery attempt failed.

    Every transport failure is this type, so the worker never has to know
    which library a transport is built on to decide that a retry is due.
    """


# ── policy ───────────────────────────────────────────────────────────────


def policy_allows(policy: str | None, kind: str) -> bool:
    """Return whether ``policy`` asks for deliveries of ``kind``."""

    allowed = _POLICY_KINDS.get(_clean_policy(policy))
    return kind in allowed if allowed else False


def resolve_notification_policy(
    project: Project | None, task: Task | None = None
) -> str:
    """Resolve the ``notification`` decision for one task.

    Resolution belongs to the canonical policy matrix, including task
    overrides, per-task-type rules, project defaults, and the built-in default.
    """

    matrix = PolicyMatrix.for_project(project)
    if task is None:
        return matrix.resolve("notification").value
    return matrix.resolve(
        "notification",
        task_type=task.task_type,
        overrides=task.executor_overrides,
    ).value


def notify_decision(
    payload: Mapping[str, Any] | None,
    *,
    project: Project | None = None,
    task: Task | None = None,
) -> str:
    """Return the notification policy that governs one event.

    The engine stamps the resolved decision on the event as ``notify`` at the
    moment it emits it, and that stamp wins: it records what the policy said
    *then*, so a project whose setting changed mid-run does not retroactively
    silence or amplify an event already written. Only an event without the
    stamp -- one written before the field existed -- falls back to resolving
    the policy now.
    """

    if isinstance(payload, Mapping):
        stamped = payload.get("notify")
        if isinstance(stamped, str) and stamped in NOTIFICATION_POLICIES:
            return stamped
    return resolve_notification_policy(project, task)


def kind_for_event(event_type: str, payload: Mapping[str, Any] | None = None) -> str | None:
    """Return the notification kind one persisted event carries, if any."""

    kind = _EVENT_KINDS.get(event_type)
    if kind is None:
        return None
    if kind == HUMAN_GATE:
        reason = (payload or {}).get("reason")
        if reason != "human_gate":
            return None
    return kind


def _clean_policy(value: Any) -> str:
    return value if isinstance(value, str) and value in NOTIFICATION_POLICIES else ""


# ── payload ──────────────────────────────────────────────────────────────


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


# ── transports ───────────────────────────────────────────────────────────


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


# ── dispatch ─────────────────────────────────────────────────────────────


class NotificationDispatcher:
    """Turn announceable events into queued deliveries.

    Called from the engine's event emission, so its contract is narrow: decide
    fast, write little, and never propagate an exception. Anything that goes
    wrong here is logged and dropped, because a project's notification setup
    is not allowed to change whether its work succeeds.
    """

    def __init__(
        self,
        store: ForemanStore,
        *,
        logger: logging.Logger | None = None,
        utc_now: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.logger = logger if logger is not None else _LOGGER
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))

    def consider(self, event: Event) -> list[NotificationDelivery]:
        """Queue deliveries for one just-persisted event.

        Returns what was queued, which is empty for the overwhelming majority
        of events. Never raises.
        """

        try:
            return self._consider(event)
        except Exception:  # pragma: no cover - defensive; see class docstring
            self.logger.warning(
                "notification dispatch failed for event %s", event.id, exc_info=True
            )
            return []

    def _consider(self, event: Event) -> list[NotificationDelivery]:
        kind = kind_for_event(event.event_type, event.payload)
        if kind is None:
            return []
        destinations = self.store.list_notification_destinations(
            event.project_id, include_disabled=False
        )
        if not destinations:
            return []

        project = self.store.get_project(event.project_id)
        if project is None:
            return []
        task = self._task_for(event)
        policy = notify_decision(event.payload, project=project, task=task)
        if not policy_allows(policy, kind):
            return []

        payload = build_payload(kind=kind, event=event, project=project, task=task)
        queued: list[NotificationDelivery] = []
        for destination in destinations:
            delivery = self.store.enqueue_notification_delivery(
                project_id=event.project_id,
                destination_id=destination.id,
                kind=kind,
                payload=payload,
                task_id=task.id if task is not None else None,
                event_id=event.id,
                next_attempt_at=_iso(self._utc_now()),
            )
            if delivery is not None:
                queued.append(delivery)
        if queued:
            self.logger.debug(
                "queued %d notification(s) for %s", len(queued), event.event_type
            )
        return queued

    def _task_for(self, event: Event) -> Task | None:
        """Return the task an event is about.

        ``engine.attention_needed`` names its subject in the payload rather
        than in the row: a sprint handoff is raised against a system run whose
        ``task_id`` is an anchor task the notification should not claim is the
        one needing attention.
        """

        payload = event.payload or {}
        if event.event_type == "engine.attention_needed":
            task_id = payload.get("task_id")
            return self.store.get_task(str(task_id)) if task_id else None
        return self.store.get_task(event.task_id) if event.task_id else None


# ── delivery ─────────────────────────────────────────────────────────────


@dataclass(slots=True)
class DrainResult:
    """What one pass of the delivery worker did."""

    attempted: int = 0
    delivered: int = 0
    retrying: int = 0
    failed: int = 0

    @property
    def did_work(self) -> bool:
        return self.attempted > 0


class NotificationDeliveryWorker:
    """Send what the dispatcher queued, and record how it went.

    Runs outside task execution -- between engine passes, or once at the end
    of a one-shot run -- so a slow or dead destination costs wall-clock in the
    worker rather than in a task. Like the dispatcher, it never raises: a
    drain that goes wrong is a logged failure and a rescheduled row.
    """

    def __init__(
        self,
        store: ForemanStore,
        *,
        transport_factory: Callable[[NotificationDestination], NotificationTransport]
        | None = None,
        utc_now: Callable[[], datetime] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.store = store
        self._transport_factory = transport_factory or build_transport
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self.logger = logger if logger is not None else _LOGGER

    def drain(
        self, project_id: str, *, limit: int = DEFAULT_DRAIN_LIMIT
    ) -> DrainResult:
        """Attempt every delivery that is due for one project."""

        result = DrainResult()
        try:
            due = self.store.list_due_notification_deliveries(
                project_id, now=_iso(self._utc_now()), limit=max(1, int(limit))
            )
        except Exception:  # pragma: no cover - defensive; see class docstring
            self.logger.warning(
                "could not read due notifications for %s", project_id, exc_info=True
            )
            return result
        for delivery in due:
            self._attempt(delivery, result)
        return result

    def _attempt(self, delivery: NotificationDelivery, result: DrainResult) -> None:
        result.attempted += 1
        destination = self.store.get_notification_destination(delivery.destination_id)
        if destination is None or not destination.enabled:
            # The destination was removed or switched off after the delivery
            # was queued. There is nowhere to send it and nothing to retry.
            self.store.settle_notification_delivery(
                delivery.id,
                status="failed",
                attempts=delivery.attempts,
                last_error="Destination is no longer enabled.",
                now=_iso(self._utc_now()),
            )
            result.failed += 1
            return

        attempts = delivery.attempts + 1
        try:
            detail = self._transport_factory(destination).send(destination, delivery)
        except Exception as exc:
            self._record_failure(delivery, destination, attempts, exc, result)
            return
        self.store.settle_notification_delivery(
            delivery.id,
            status="delivered",
            attempts=attempts,
            last_error=None,
            now=_iso(self._utc_now()),
        )
        result.delivered += 1
        self.logger.debug(
            "delivered notification %s to %s (%s)", delivery.id, destination.name, detail
        )

    def _record_failure(
        self,
        delivery: NotificationDelivery,
        destination: NotificationDestination,
        attempts: int,
        exc: BaseException,
        result: DrainResult,
    ) -> None:
        """Reschedule a failed attempt, or give up and leave the reason behind."""

        error = f"{type(exc).__name__}: {exc}"
        now = self._utc_now()
        if attempts >= max(1, delivery.max_attempts):
            self.store.settle_notification_delivery(
                delivery.id,
                status="failed",
                attempts=attempts,
                last_error=error,
                now=_iso(now),
            )
            result.failed += 1
            # The row already records this, but a run's own event stream is
            # where an operator looks first, and "nobody was told" is exactly
            # the kind of silent outcome that has to be visible somewhere
            # noisy.
            self._record_giving_up(delivery, destination, attempts, error)
            self.logger.warning(
                "notification %s to %s failed after %d attempts: %s",
                delivery.id,
                destination.name,
                attempts,
                error,
            )
            return
        self.store.settle_notification_delivery(
            delivery.id,
            status="pending",
            attempts=attempts,
            last_error=error,
            now=_iso(now),
            next_attempt_at=_iso(now + timedelta(seconds=retry_delay_seconds(attempts))),
        )
        result.retrying += 1
        self.logger.info(
            "notification %s to %s failed (attempt %d), retrying: %s",
            delivery.id,
            destination.name,
            attempts,
            error,
        )

    def _record_giving_up(
        self,
        delivery: NotificationDelivery,
        destination: NotificationDestination,
        attempts: int,
        error: str,
    ) -> None:
        """Write the ``notification.failed`` event for an exhausted delivery.

        Attached to the run that produced the announceable moment: an event
        belongs to a run, and the run that raised the attention turn nobody
        heard about is the one an operator will be reading. A delivery with no
        run behind it -- a ``foreman notify test``, a project-level event --
        has only the row and the log, which is what those callers watch.
        """

        run_id = str((delivery.payload.get("event") or {}).get("run_id") or "")
        if not run_id:
            return
        try:
            self.store.save_event(
                Event(
                    id=f"event-{uuid4().hex[:12]}",
                    run_id=run_id,
                    task_id=delivery.task_id or "",
                    project_id=delivery.project_id,
                    event_type="notification.failed",
                    payload={
                        "schema_version": PAYLOAD_SCHEMA_VERSION,
                        "delivery_id": delivery.id,
                        "destination_id": destination.id,
                        "destination": destination.name,
                        "kind": delivery.kind,
                        "attempts": attempts,
                        "error": error,
                    },
                )
            )
        except Exception:  # pragma: no cover - defensive; see class docstring
            self.logger.warning(
                "could not record notification failure %s", delivery.id, exc_info=True
            )


def retry_delay_seconds(attempts: int) -> float:
    """Seconds to wait before attempt ``attempts + 1``."""

    exponent = max(0, int(attempts) - 1)
    return min(RETRY_BASE_SECONDS * (2**exponent), RETRY_MAX_SECONDS)


# ── destination validation ───────────────────────────────────────────────


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
    store: "ForemanStore",
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


def _iso(moment: datetime) -> str:
    """Format a moment the way every other timestamp in the store is stored.

    Microsecond precision matters here: ``next_attempt_at`` is compared as a
    string against other stored timestamps, so the two must agree on shape.
    """

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (
        moment.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
