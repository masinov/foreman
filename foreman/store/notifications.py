"""Notification destinations and the delivery outbox."""

from __future__ import annotations

import sqlite3
from typing import Any
from uuid import uuid4

from ..models import (
    NotificationDelivery,
    NotificationDestination,
    utc_now_text,
)

from .base import (
    StoreBase,
)
from .rows import (
    _json_dumps,
    _row_to_notification_delivery,
    _row_to_notification_destination,
)


class NotificationStore(StoreBase):
    """Notification destinations and the delivery outbox."""

    def save_notification_destination(
        self, destination: NotificationDestination
    ) -> NotificationDestination:
        """Insert or update one notification destination.

        Upsert on the primary key like every other ``save_*``: the caller owns
        the identifier, so editing a destination is reading it, changing a
        field, and saving it back.
        """

        destination.updated_at = utc_now_text()

        def _write(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO notification_destinations (
                    id, project_id, name, kind, target, config_json, enabled,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    kind = excluded.kind,
                    target = excluded.target,
                    config_json = excluded.config_json,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    destination.id,
                    destination.project_id,
                    destination.name,
                    destination.kind,
                    destination.target,
                    _json_dumps(destination.config),
                    1 if destination.enabled else 0,
                    destination.created_at,
                    destination.updated_at,
                ),
            )

        self._write(_write)
        return destination

    def get_notification_destination(
        self, destination_id: str
    ) -> NotificationDestination | None:
        """Return one destination by identifier, enabled or not."""

        row = self._connection.execute(
            "SELECT * FROM notification_destinations WHERE id = ?",
            (destination_id,),
        ).fetchone()
        return _row_to_notification_destination(row) if row else None

    def find_notification_destination(
        self, project_id: str, name: str
    ) -> NotificationDestination | None:
        """Return one destination by the name a person refers to it by."""

        row = self._connection.execute(
            "SELECT * FROM notification_destinations WHERE project_id = ? AND name = ?",
            (project_id, (name or "").strip()),
        ).fetchone()
        return _row_to_notification_destination(row) if row else None

    def list_notification_destinations(
        self, project_id: str, *, include_disabled: bool = True
    ) -> list[NotificationDestination]:
        """List a project's destinations, oldest first.

        The dispatcher calls this on every announceable event, so the default
        for its caller is ``include_disabled=False``: a disabled destination
        must not accumulate a queue it will never be sent.
        """

        query = "SELECT * FROM notification_destinations WHERE project_id = ?"
        if not include_disabled:
            query += " AND enabled = 1"
        query += " ORDER BY created_at ASC, id ASC"
        rows = self._connection.execute(query, (project_id,)).fetchall()
        return [_row_to_notification_destination(row) for row in rows]

    def delete_notification_destination(self, destination_id: str) -> bool:
        """Delete one destination and everything queued for it.

        A removed destination has no address, so its pending rows are not work
        anyone can do. Delivered and failed rows go with it: they are the
        history of a destination that no longer exists, and keeping orphans
        would make the delivery log unreadable.
        """

        existing = self.get_notification_destination(destination_id)
        if existing is None:
            return False

        def _write(connection: sqlite3.Connection) -> None:
            connection.execute(
                "DELETE FROM notification_deliveries WHERE destination_id = ?",
                (destination_id,),
            )
            connection.execute(
                "DELETE FROM notification_destinations WHERE id = ?",
                (destination_id,),
            )

        self._write(_write)
        return True

    def enqueue_notification_delivery(
        self,
        *,
        project_id: str,
        destination_id: str,
        kind: str,
        payload: dict[str, Any],
        task_id: str | None = None,
        event_id: str | None = None,
        next_attempt_at: str | None = None,
        max_attempts: int = 5,
    ) -> NotificationDelivery | None:
        """Queue one delivery, or return None when it is already queued.

        ``event_id`` makes the insert idempotent through the unique index: the
        same event offered twice for the same destination -- a retried pass,
        two engines racing -- yields one delivery, which is the acceptance
        criterion the caller is trying to meet.
        """

        now = utc_now_text()
        delivery = NotificationDelivery(
            id=f"ntf-{uuid4().hex[:12]}",
            project_id=project_id,
            destination_id=destination_id,
            kind=kind,
            payload=dict(payload),
            task_id=task_id,
            event_id=event_id,
            next_attempt_at=next_attempt_at or now,
            max_attempts=max(1, int(max_attempts)),
            created_at=now,
            updated_at=now,
        )

        def _write(connection: sqlite3.Connection) -> int:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO notification_deliveries (
                    id, project_id, destination_id, task_id, event_id, kind,
                    payload_json, status, attempts, max_attempts,
                    next_attempt_at, last_error, created_at, updated_at,
                    delivered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, NULL, ?, ?, NULL)
                """,
                (
                    delivery.id,
                    delivery.project_id,
                    delivery.destination_id,
                    delivery.task_id,
                    delivery.event_id,
                    delivery.kind,
                    _json_dumps(delivery.payload),
                    delivery.max_attempts,
                    delivery.next_attempt_at,
                    delivery.created_at,
                    delivery.updated_at,
                ),
            )
            return cursor.rowcount

        return delivery if self._write(_write) else None

    def get_notification_delivery(self, delivery_id: str) -> NotificationDelivery | None:
        """Return one delivery by identifier."""

        row = self._connection.execute(
            "SELECT * FROM notification_deliveries WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        return _row_to_notification_delivery(row) if row else None

    def list_due_notification_deliveries(
        self, project_id: str, *, now: str, limit: int = 20
    ) -> list[NotificationDelivery]:
        """List the pending deliveries whose next attempt is due, oldest first.

        ``now`` is passed in rather than read here so the caller owns the
        clock: the delivery worker is driven by an injectable one, which is
        what makes a backoff schedule testable without sleeping through it.
        """

        rows = self._connection.execute(
            """
            SELECT * FROM notification_deliveries
            WHERE project_id = ? AND status = 'pending' AND next_attempt_at <= ?
            ORDER BY next_attempt_at ASC, created_at ASC, id ASC
            LIMIT ?
            """,
            (project_id, now, max(1, int(limit))),
        ).fetchall()
        return [_row_to_notification_delivery(row) for row in rows]

    def list_notification_deliveries(
        self,
        project_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[NotificationDelivery]:
        """List a project's deliveries, most recent first, for an operator."""

        query = "SELECT * FROM notification_deliveries WHERE project_id = ?"
        params: list[Any] = [project_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, int(limit)))
        rows = self._connection.execute(query, tuple(params)).fetchall()
        return [_row_to_notification_delivery(row) for row in rows]

    def settle_notification_delivery(
        self,
        delivery_id: str,
        *,
        status: str,
        attempts: int,
        last_error: str | None,
        now: str,
        next_attempt_at: str | None = None,
    ) -> NotificationDelivery | None:
        """Record the outcome of one delivery attempt.

        One method for all three outcomes -- delivered, retrying, given up --
        because they differ only in the status they land on and whether a next
        attempt is scheduled. ``delivered_at`` is set only by success, so it
        keeps meaning "when this actually arrived".
        """

        if status not in ("pending", "delivered", "failed"):
            raise ValueError(
                f"Unknown notification delivery status: {status}. "
                "Expected pending, delivered, or failed."
            )
        existing = self.get_notification_delivery(delivery_id)
        if existing is None:
            return None
        delivered_at = now if status == "delivered" else existing.delivered_at
        scheduled = next_attempt_at or existing.next_attempt_at

        def _write(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                UPDATE notification_deliveries
                SET status = ?, attempts = ?, last_error = ?, next_attempt_at = ?,
                    updated_at = ?, delivered_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    max(0, int(attempts)),
                    last_error,
                    scheduled,
                    now,
                    delivered_at,
                    delivery_id,
                ),
            )

        self._write(_write)
        existing.status = status
        existing.attempts = max(0, int(attempts))
        existing.last_error = last_error
        existing.next_attempt_at = scheduled
        existing.updated_at = now
        existing.delivered_at = delivered_at
        return existing

    def count_notification_deliveries(self, project_id: str) -> dict[str, int]:
        """Return a project's delivery counts by status, for status surfaces."""

        rows = self._connection.execute(
            """
            SELECT status, COUNT(*) AS total FROM notification_deliveries
            WHERE project_id = ? GROUP BY status
            """,
            (project_id,),
        ).fetchall()
        counts = {"pending": 0, "delivered": 0, "failed": 0}
        for row in rows:
            counts[row["status"]] = int(row["total"])
        return counts
