"""Queueing a message for each destination, and the worker that delivers the queue
with retries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

from ..domain.models import Event, NotificationDelivery, NotificationDestination, Task
from ..store import ForemanStore
from .policy import kind_for_event, notify_decision, policy_allows
from .transport import (
    PAYLOAD_SCHEMA_VERSION,
    NotificationTransport,
    build_payload,
    build_transport,
)

_LOGGER = logging.getLogger("foreman.notifications")


#: Retry schedule. Attempt *n* waits ``BASE * 2**(n-1)``, capped, so a
#: destination that is briefly down is caught within a minute and one that is
#: down for an afternoon is not hammered.
RETRY_BASE_SECONDS = 30.0


RETRY_MAX_SECONDS = 1800.0


DEFAULT_MAX_ATTEMPTS = 5


#: How many deliveries one drain sends before returning to the caller. Bounds
#: the worst case a slow destination can add to a pass.
DEFAULT_DRAIN_LIMIT = 20


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
