"""The manager chat's sessions and turns."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..models import (
    utc_now_text,
)

from .base import (
    StoreBase,
    retried_on_lock,
)


class MetaSessionStore(StoreBase):
    """The manager chat's sessions and turns."""

    def get_meta_session(self, project_id: str) -> str | None:
        """Return the stored Claude Code resume session id for a project, if any."""
        row = self._connection.execute(
            "SELECT session_id FROM meta_sessions WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return row["session_id"] if row else None

    @retried_on_lock
    def save_meta_session(self, project_id: str, session_id: str | None) -> None:
        """Upsert the meta-agent resume session id for a project."""
        now = utc_now_text()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO meta_sessions (project_id, session_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    updated_at = excluded.updated_at
                """,
                (project_id, session_id, now),
            )

    @retried_on_lock
    def append_meta_turn(
        self,
        project_id: str,
        *,
        role: str,
        text: str,
        tool_uses: list[dict[str, Any]] | None = None,
        origin: str = "chat",
    ) -> str:
        """Append one conversation turn and return its generated id."""
        import json as _json

        turn_id = uuid4().hex
        now = utc_now_text()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO meta_turns (
                    id, project_id, role, text, tool_uses_json, origin, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    project_id,
                    role,
                    text,
                    _json.dumps(tool_uses or []),
                    origin,
                    now,
                ),
            )
        return turn_id

    def list_meta_turns(
        self,
        project_id: str,
        *,
        limit: int = 50,
        before_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Return up to ``limit`` turns oldest-first plus a ``has_more`` flag.

        When ``before_id`` is given, returns turns created strictly before that
        turn (older history), supporting cursor-based "load older" paging that
        mirrors the sprint-event endpoint.
        """
        import json as _json

        params: list[Any] = [project_id]
        cursor_clause = ""
        if before_id is not None:
            anchor = self._connection.execute(
                "SELECT created_at FROM meta_turns WHERE id = ?",
                (before_id,),
            ).fetchone()
            if anchor is not None:
                cursor_clause = " AND (created_at < ? OR (created_at = ? AND id < ?))"
                params.extend([anchor["created_at"], anchor["created_at"], before_id])

        # Fetch newest-first with one extra row to detect more history, then
        # reverse so callers receive turns in chronological order.
        params.append(limit + 1)
        rows = self._connection.execute(
            f"""
            SELECT id, role, text, tool_uses_json, origin, created_at
            FROM meta_turns
            WHERE project_id = ?{cursor_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

        has_more = len(rows) > limit
        rows = rows[:limit]
        turns = [
            {
                "id": row["id"],
                "role": row["role"],
                "text": row["text"],
                "tool_uses": _json.loads(row["tool_uses_json"] or "[]"),
                "origin": row["origin"],
                "created_at": row["created_at"],
            }
            for row in reversed(rows)
        ]
        return turns, has_more

    def has_consumed_supervision_event(self, project_id: str, event_id: str) -> bool:
        """Return True if a supervision turn already consumed ``event_id``.

        Idempotency guard for the supervise endpoint: the consumed
        ``engine.attention_needed`` event id is stored in the user turn's
        ``tool_uses_json`` metadata.
        """
        like = f'%"consumed_event_id": "{event_id}"%'
        row = self._connection.execute(
            """
            SELECT 1 FROM meta_turns
            WHERE project_id = ? AND origin = 'supervision'
              AND tool_uses_json LIKE ?
            LIMIT 1
            """,
            (project_id, like),
        ).fetchone()
        return row is not None

    @retried_on_lock
    def clear_meta_session(self, project_id: str) -> None:
        """Delete the stored session row and all turns for a project."""
        with self._connection:
            self._connection.execute(
                "DELETE FROM meta_turns WHERE project_id = ?", (project_id,)
            )
            self._connection.execute(
                "DELETE FROM meta_sessions WHERE project_id = ?", (project_id,)
            )
