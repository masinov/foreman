"""A user's holds on work (ADR-0043): a task's pause, and blocks on a sprint
or the workspace.

A pause is four columns of ``tasks`` that only these methods write, so the
engine's writes (``update_task_engine_state``) and a task object read
before a user paused it can never lift a pause. A block on a sprint or the
workspace is a row of ``holds``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from ..domain.holds import PAUSABLE_TASK_STATUSES, WORKSPACE_SCOPE_ID, LevelBlock
from .base import StoreBase


def _block_from_row(row: sqlite3.Row) -> LevelBlock:
    return LevelBlock(
        scope=row["scope"],
        scope_id=row["scope_id"],
        project_id=row["project_id"],
        reason=row["reason"],
        set_by=row["set_by"],
        set_at=row["set_at"],
    )


def _placeholders(values: list[str]) -> str:
    return ", ".join("?" for _ in values)


class HoldStore(StoreBase):
    """Pauses on tasks and blocks on sprints and the workspace."""

    # ── Task pauses ──────────────────────────────────────────────────────

    def pause_tasks(
        self,
        task_ids: Iterable[str],
        *,
        by: str,
        at: str,
        mode: str,
    ) -> list[str]:
        """Pause the given tasks that may be paused. Returns the ids paused.

        A task already paused keeps who paused it and when; a Stop (``now``)
        still turns its pause into a cut, so the step it runs is ended. A
        finished, filed or cancelled task is left alone.
        """

        ids = list(dict.fromkeys(task_ids))
        if not ids:
            return []
        statuses = sorted(PAUSABLE_TASK_STATUSES)

        def _write(connection: sqlite3.Connection) -> list[str]:
            rows = connection.execute(
                f"SELECT id FROM tasks WHERE id IN ({_placeholders(ids)}) "
                f"AND status IN ({_placeholders(statuses)})",
                (*ids, *statuses),
            ).fetchall()
            changed = [row["id"] for row in rows]
            if not changed:
                return []
            connection.execute(
                f"""
                UPDATE tasks
                SET paused_at = COALESCE(paused_at, ?),
                    paused_by = COALESCE(paused_by, ?),
                    pause_mode = CASE
                        WHEN ? = 'now' THEN 'now'
                        ELSE COALESCE(pause_mode, ?)
                    END
                WHERE id IN ({_placeholders(changed)})
                """,
                (at, by, mode, mode, *changed),
            )
            return changed

        return self._write(_write)

    def resume_tasks(self, task_ids: Iterable[str]) -> list[str]:
        """Lift the pause of the given tasks. Returns the ids resumed.

        A task whose Block waits for its step to end is not resumed: only
        Unblock lifts a block.
        """

        ids = list(dict.fromkeys(task_ids))
        if not ids:
            return []

        def _write(connection: sqlite3.Connection) -> list[str]:
            rows = connection.execute(
                f"SELECT id FROM tasks WHERE id IN ({_placeholders(ids)}) "
                "AND paused_at IS NOT NULL AND block_requested IS NULL",
                ids,
            ).fetchall()
            changed = [row["id"] for row in rows]
            if changed:
                connection.execute(
                    "UPDATE tasks SET paused_at = NULL, paused_by = NULL, "
                    f"pause_mode = NULL WHERE id IN ({_placeholders(changed)})",
                    changed,
                )
            return changed

        return self._write(_write)

    def clear_task_hold(self, task_id: str) -> None:
        """Forget a task's pause and any Block waiting for its step.

        For a task that moved to another sprint or the backlog, was closed
        or reopened: a hold does not outlive what it was set on.
        """

        self._write(
            lambda connection: connection.execute(
                "UPDATE tasks SET paused_at = NULL, paused_by = NULL, "
                "pause_mode = NULL, block_requested = NULL WHERE id = ?",
                (task_id,),
            )
        )

    def request_task_block(self, task_id: str, *, reason: str, by: str, at: str) -> None:
        """Hold a running task and block it with ``reason`` once its step ends."""

        self._write(
            lambda connection: connection.execute(
                """
                UPDATE tasks
                SET block_requested = ?,
                    paused_at = COALESCE(paused_at, ?),
                    paused_by = COALESCE(paused_by, ?),
                    pause_mode = COALESCE(pause_mode, 'finish_step')
                WHERE id = ?
                """,
                (reason, at, by, task_id),
            )
        )

    def withdraw_task_block_request(self, task_id: str) -> bool:
        """Unblock a task whose Block was still waiting for its step to end."""

        def _write(connection: sqlite3.Connection) -> bool:
            cursor = connection.execute(
                "UPDATE tasks SET block_requested = NULL, paused_at = NULL, "
                "paused_by = NULL, pause_mode = NULL "
                "WHERE id = ? AND block_requested IS NOT NULL",
                (task_id,),
            )
            return cursor.rowcount > 0

        return self._write(_write)

    def apply_requested_block(self, task_id: str) -> str | None:
        """Block a task whose requested Block was waiting for its step to end.

        The engine calls it when the step has ended. Returns the reason, or
        None when there was no Block waiting (a user unblocked it meanwhile).
        """

        def _write(connection: sqlite3.Connection) -> str | None:
            row = connection.execute(
                "SELECT block_requested FROM tasks WHERE id = ? "
                "AND block_requested IS NOT NULL AND status != 'cancelled'",
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE tasks
                SET status = 'blocked', blocked_reason = block_requested,
                    block_requested = NULL, paused_at = NULL, paused_by = NULL,
                    pause_mode = NULL,
                    -- Unblock starts the workflow over; a step left here could
                    -- read as a gate waiting for a decision.
                    workflow_current_step = NULL, workflow_carried_output = NULL
                WHERE id = ?
                """,
                (task_id,),
            )
            return str(row["block_requested"])

        return self._write(_write)

    # ── Blocks on a sprint or the workspace ──────────────────────────────

    def get_level_block(self, scope: str, scope_id: str) -> LevelBlock | None:
        row = self._connection.execute(
            "SELECT * FROM holds WHERE scope = ? AND scope_id = ?",
            (scope, scope_id),
        ).fetchone()
        return _block_from_row(row) if row is not None else None

    def get_sprint_block(self, sprint_id: str | None) -> LevelBlock | None:
        if not sprint_id:
            return None
        return self.get_level_block("sprint", sprint_id)

    def get_workspace_block(self) -> LevelBlock | None:
        return self.get_level_block("workspace", WORKSPACE_SCOPE_ID)

    def list_level_blocks(self) -> list[LevelBlock]:
        rows = self._connection.execute(
            "SELECT * FROM holds ORDER BY set_at"
        ).fetchall()
        return [_block_from_row(row) for row in rows]

    def set_level_block(self, block: LevelBlock) -> LevelBlock:
        """Set a block. A level already blocked keeps its first block."""

        def _write(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO holds (scope, scope_id, project_id, reason, set_by, set_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, scope_id) DO NOTHING
                """,
                (
                    block.scope,
                    block.scope_id,
                    block.project_id,
                    block.reason,
                    block.set_by,
                    block.set_at,
                ),
            )

        self._write(_write)
        stored = self.get_level_block(block.scope, block.scope_id)
        assert stored is not None
        return stored

    def delete_level_block(self, scope: str, scope_id: str) -> bool:
        """Lift a block. False when there was none."""

        def _write(connection: sqlite3.Connection) -> bool:
            cursor = connection.execute(
                "DELETE FROM holds WHERE scope = ? AND scope_id = ?",
                (scope, scope_id),
            )
            return cursor.rowcount > 0

        return self._write(_write)
