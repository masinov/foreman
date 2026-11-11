"""Events and the queries the activity feeds use."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..models import (
    Event,
)

from .base import (
    StoreBase,
    _PRUNE_PROTECTED_TASK_STATUSES,
    retried_on_lock,
)
from .rows import (
    _json_dumps,
    _row_to_event,
)


class EventStore(StoreBase):
    """Events and the queries the activity feeds use."""

    def get_latest_event_timestamp(self, run_id: str) -> str | None:
        """Return the latest persisted event timestamp for one run, if any."""

        row = self._connection.execute(
            """
            SELECT timestamp FROM events
            WHERE run_id = ?
            ORDER BY timestamp DESC, rowid DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        timestamp = row["timestamp"]
        return str(timestamp) if timestamp else None

    def save_event(self, event: Event) -> Event:
        """Insert or update an event record."""

        def _write_event(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO events (
                    id, run_id, task_id, project_id, event_type, role_id, timestamp,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    run_id = excluded.run_id,
                    task_id = excluded.task_id,
                    project_id = excluded.project_id,
                    event_type = excluded.event_type,
                    role_id = excluded.role_id,
                    timestamp = excluded.timestamp,
                    payload_json = excluded.payload_json
                """,
                (
                    event.id,
                    event.run_id,
                    event.task_id,
                    event.project_id,
                    event.event_type,
                    event.role_id,
                    event.timestamp,
                    _json_dumps(event.payload),
                ),
            )

        self._write(_write_event)
        return event

    def get_event(self, event_id: str) -> Event | None:
        """Return one event by identifier."""

        row = self._connection.execute(
            "SELECT * FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        return _row_to_event(row) if row else None

    def _get_event_cursor_marker(self, event_id: str) -> sqlite3.Row | None:
        """Return the timestamp and rowid used for incremental event queries."""

        return self._connection.execute(
            "SELECT timestamp, rowid FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()

    def has_event(self, *, task_id: str, event_type: str) -> bool:
        """Return whether one task has already recorded an event of this type.

        Used for events that must be written once per task (the resolved
        policy matrix), which would otherwise be re-emitted every time a task
        resumes.
        """

        row = self._connection.execute(
            "SELECT 1 FROM events WHERE task_id = ? AND event_type = ? LIMIT 1",
            (task_id, event_type),
        ).fetchone()
        return row is not None

    def list_events(
        self,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        project_id: str | None = None,
        after_event_id: str | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """List events filtered by run, task, and or project."""

        filters: list[str] = []
        params: list[Any] = []
        if run_id is not None:
            filters.append("e.run_id = ?")
            params.append(run_id)
        if task_id is not None:
            filters.append("e.task_id = ?")
            params.append(task_id)
        if project_id is not None:
            filters.append("e.project_id = ?")
            params.append(project_id)
        if after_event_id is not None:
            marker = self._get_event_cursor_marker(after_event_id)
            if marker is None:
                return []
            filters.append(
                """
                (
                    e.timestamp > ?
                    OR (e.timestamp = ? AND e.rowid > ?)
                )
                """
            )
            params.extend([marker["timestamp"], marker["timestamp"], marker["rowid"]])

        sql = "SELECT e.* FROM events e"
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"{sql} ORDER BY e.timestamp ASC, e.rowid ASC"
        if limit is not None:
            sql = f"{sql} LIMIT ?"
            params.append(limit)

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_sprint_events(
        self,
        sprint_id: str,
        *,
        after_event_id: str | None = None,
        before_event_id: str | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """List sprint-scoped events in display order.

        Pass ``after_event_id`` to fetch events newer than a known cursor
        (used by the SSE stream to deliver incremental updates).
        Pass ``before_event_id`` to fetch events older than a known cursor
        (used by the activity panel load-more control).
        """

        params: list[Any] = [sprint_id]

        if after_event_id is not None:
            marker = self._get_event_cursor_marker(after_event_id)
            if marker is None:
                return []
            sql = """
                SELECT e.*
                FROM events e
                INNER JOIN tasks t ON t.id = e.task_id
                WHERE t.sprint_id = ?
                AND (
                    e.timestamp > ?
                    OR (e.timestamp = ? AND e.rowid > ?)
                )
                ORDER BY e.timestamp ASC, e.rowid ASC
            """
            params.extend([marker["timestamp"], marker["timestamp"], marker["rowid"]])
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            rows = self._connection.execute(sql, tuple(params)).fetchall()
            return [_row_to_event(row) for row in rows]

        if before_event_id is not None:
            marker = self._get_event_cursor_marker(before_event_id)
            if marker is None:
                return []
            sql = """
                SELECT e.*
                FROM events e
                INNER JOIN tasks t ON t.id = e.task_id
                WHERE t.sprint_id = ?
                AND (
                    e.timestamp < ?
                    OR (e.timestamp = ? AND e.rowid < ?)
                )
                ORDER BY e.timestamp DESC, e.rowid DESC
            """
            params.extend([marker["timestamp"], marker["timestamp"], marker["rowid"]])
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            rows = self._connection.execute(sql, tuple(params)).fetchall()
            events = [_row_to_event(row) for row in rows]
            events.reverse()
            return events

        # No cursor — return all events in display order, optionally limited.
        sql = """
            SELECT e.*
            FROM events e
            INNER JOIN tasks t ON t.id = e.task_id
            WHERE t.sprint_id = ?
            ORDER BY e.timestamp ASC, e.rowid ASC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_recent_sprint_events(self, sprint_id: str, *, limit: int = 50) -> list[Event]:
        """Return the most recent sprint events while preserving display order."""

        if limit <= 0:
            return []

        rows = self._connection.execute(
            """
            SELECT e.*
            FROM events e
            INNER JOIN tasks t ON t.id = e.task_id
            WHERE t.sprint_id = ?
            ORDER BY e.timestamp DESC, e.rowid DESC
            LIMIT ?
            """,
            (sprint_id, limit),
        ).fetchall()
        events = [_row_to_event(row) for row in rows]
        events.reverse()
        return events

    def list_recent_events(
        self,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
    ) -> list[Event]:
        """Return the most recent events while preserving display order."""

        if limit <= 0:
            return []

        filters: list[str] = []
        params: list[Any] = []
        if run_id is not None:
            filters.append("run_id = ?")
            params.append(run_id)
        if task_id is not None:
            filters.append("task_id = ?")
            params.append(task_id)
        if project_id is not None:
            filters.append("project_id = ?")
            params.append(project_id)

        sql = "SELECT * FROM events"
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"{sql} ORDER BY timestamp DESC, rowid DESC LIMIT ?"
        params.append(limit)

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        events = [_row_to_event(row) for row in rows]
        events.reverse()
        return events

    @retried_on_lock
    def prune_old_events(
        self,
        *,
        project_id: str,
        older_than: str,
    ) -> int:
        """Delete project events older than one cutoff while preserving active-work history."""

        with self._connection:
            cursor = self._connection.execute(
                f"""
                DELETE FROM events
                WHERE project_id = ?
                  AND timestamp < ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM tasks
                      WHERE tasks.id = events.task_id
                        AND tasks.status IN ({", ".join("?" for _ in _PRUNE_PROTECTED_TASK_STATUSES)})
                  )
                """,
                (
                    project_id,
                    older_than,
                    *_PRUNE_PROTECTED_TASK_STATUSES,
                ),
            )
        return int(cursor.rowcount)
