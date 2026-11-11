"""Commands queued for a project's resident engine."""

from __future__ import annotations

import sqlite3
from typing import Any
from uuid import uuid4

from ..models import (
    ENGINE_COMMAND_STATUSES,
    ENGINE_COMMANDS,
    EngineCommand,
    utc_now_text,
)

from .base import (
    StoreBase,
)
from .rows import (
    _row_to_engine_command,
)


class EngineCommandStore(StoreBase):
    """Commands queued for a project's resident engine."""

    def enqueue_engine_command(
        self,
        *,
        project_id: str,
        command: str,
        requested_by: str,
        task_id: str | None = None,
        command_id: str | None = None,
    ) -> EngineCommand:
        """Queue one control instruction for the project's resident engine.

        The insert commits on this connection, which bumps ``PRAGMA
        data_version`` for every *other* connection — so a resident engine
        sitting in its idle wait notices the command without polling any table.
        """

        if command not in ENGINE_COMMANDS:
            raise ValueError(
                f"Unknown engine command {command!r}. "
                f"Expected one of: {', '.join(ENGINE_COMMANDS)}."
            )
        record = EngineCommand(
            id=command_id or f"cmd-{uuid4().hex[:12]}",
            project_id=project_id,
            command=command,  # type: ignore[arg-type]
            requested_by=requested_by,
            task_id=task_id,
        )

        def _write(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO engine_commands (
                    id, project_id, command, task_id, requested_by, requested_at,
                    status, acknowledged_at, completed_at, result_detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.project_id,
                    record.command,
                    record.task_id,
                    record.requested_by,
                    record.requested_at,
                    record.status,
                    record.acknowledged_at,
                    record.completed_at,
                    record.result_detail,
                ),
            )

        self._write(_write)
        return record

    def get_engine_command(self, command_id: str) -> EngineCommand | None:
        """Return one engine command by identifier."""

        row = self._connection.execute(
            "SELECT * FROM engine_commands WHERE id = ?",
            (command_id,),
        ).fetchone()
        return _row_to_engine_command(row) if row else None

    def list_engine_commands(
        self,
        project_id: str,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[EngineCommand]:
        """List a project's engine commands, most recently requested first."""

        conditions = ["project_id = ?"]
        params: list[Any] = [project_id]
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        params.append(max(0, int(limit)))
        rows = self._connection.execute(
            f"""
            SELECT * FROM engine_commands
            WHERE {' AND '.join(conditions)}
            ORDER BY requested_at DESC, rowid DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_row_to_engine_command(row) for row in rows]

    def next_pending_engine_command(self, project_id: str) -> EngineCommand | None:
        """Return the oldest pending command for a project, or None.

        Ordering is by request time so commands are applied in the order they
        were asked for; ``rowid`` breaks ties between two commands queued
        inside the same timestamp tick.
        """

        row = self._connection.execute(
            """
            SELECT * FROM engine_commands
            WHERE project_id = ? AND status = 'pending'
            ORDER BY requested_at ASC, rowid ASC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return _row_to_engine_command(row) if row else None

    def mark_engine_command(
        self,
        command_id: str,
        status: str,
        *,
        detail: str | None = None,
    ) -> EngineCommand | None:
        """Advance one command's lifecycle and record why.

        ``acknowledged`` stamps ``acknowledged_at``; ``completed`` and
        ``rejected`` stamp ``completed_at``. Returns the updated row, or None
        when the command no longer exists.
        """

        if status not in ENGINE_COMMAND_STATUSES:
            raise ValueError(
                f"Unknown engine command status {status!r}. "
                f"Expected one of: {', '.join(ENGINE_COMMAND_STATUSES)}."
            )
        now = utc_now_text()

        def _write(connection: sqlite3.Connection) -> None:
            assignments = ["status = ?"]
            params: list[Any] = [status]
            if status == "acknowledged":
                assignments.append("acknowledged_at = ?")
                params.append(now)
            elif status in {"completed", "rejected"}:
                assignments.append("completed_at = ?")
                params.append(now)
            if detail is not None:
                assignments.append("result_detail = ?")
                params.append(detail)
            params.append(command_id)
            connection.execute(
                f"UPDATE engine_commands SET {', '.join(assignments)} WHERE id = ?",
                tuple(params),
            )

        self._write(_write)
        return self.get_engine_command(command_id)
