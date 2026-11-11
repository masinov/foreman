"""Runs, their totals and their retention."""

from __future__ import annotations

import sqlite3
from typing import Any, Sequence

from ..models import (
    Run,
)

from .base import (
    StoreBase,
    _PRUNE_PROTECTED_TASK_STATUSES,
    retried_on_lock,
)
from .rows import (
    _row_to_run,
    _token_usage_from_row,
)


class RunStore(StoreBase):
    """Runs, their totals and their retention."""

    def save_run(self, run: Run) -> Run:
        """Insert or update a run record."""

        def _write_run(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO runs (
                    id, task_id, project_id, role_id, workflow_step, status, outcome,
                    outcome_detail, agent_backend, model, session_id, branch_name,
                    prompt_text, cost_usd, token_count, duration_ms, retry_count,
                    failure_type, started_at, completed_at, created_at,
                    input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    task_id = excluded.task_id,
                    project_id = excluded.project_id,
                    role_id = excluded.role_id,
                    workflow_step = excluded.workflow_step,
                    status = excluded.status,
                    outcome = excluded.outcome,
                    outcome_detail = excluded.outcome_detail,
                    agent_backend = excluded.agent_backend,
                    model = excluded.model,
                    session_id = excluded.session_id,
                    branch_name = excluded.branch_name,
                    prompt_text = excluded.prompt_text,
                    cost_usd = excluded.cost_usd,
                    token_count = excluded.token_count,
                    duration_ms = excluded.duration_ms,
                    retry_count = excluded.retry_count,
                    failure_type = excluded.failure_type,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    created_at = excluded.created_at,
                    input_tokens = excluded.input_tokens,
                    output_tokens = excluded.output_tokens,
                    cache_read_tokens = excluded.cache_read_tokens,
                    cache_creation_tokens = excluded.cache_creation_tokens
                """,
                (
                    run.id,
                    run.task_id,
                    run.project_id,
                    run.role_id,
                    run.workflow_step,
                    run.status,
                    run.outcome,
                    run.outcome_detail,
                    run.agent_backend,
                    run.model,
                    run.session_id,
                    run.branch_name,
                    run.prompt_text,
                    run.cost_usd,
                    run.token_count,
                    run.duration_ms,
                    run.retry_count,
                    run.failure_type,
                    run.started_at,
                    run.completed_at,
                    run.created_at,
                    run.token_usage.input,
                    run.token_usage.output,
                    run.token_usage.cache_read,
                    run.token_usage.cache_creation,
                ),
            )

        self._write(_write_run)
        return run

    def get_run(self, run_id: str) -> Run | None:
        """Return one run by identifier."""

        row = self._connection.execute(
            "SELECT * FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        return _row_to_run(row) if row else None

    def list_runs(
        self,
        *,
        task_id: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        statuses: Sequence[str] | None = None,
    ) -> list[Run]:
        """List runs filtered by task and or project."""

        filters: list[str] = []
        params: list[Any] = []
        if status is not None and statuses is not None:
            raise ValueError("Provide either status or statuses, not both.")
        if task_id is not None:
            filters.append("task_id = ?")
            params.append(task_id)
        if project_id is not None:
            filters.append("project_id = ?")
            params.append(project_id)
        if status is not None:
            statuses = (status,)
        if statuses is not None:
            placeholders = ", ".join("?" for _ in statuses)
            filters.append(f"status IN ({placeholders})")
            params.extend(statuses)

        sql = "SELECT * FROM runs"
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"{sql} ORDER BY created_at ASC, rowid ASC"

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_run(row) for row in rows]

    def get_latest_run(self, task_id: str) -> Run | None:
        """Return the most recent run for one task, if it exists."""

        row = self._connection.execute(
            """
            SELECT * FROM runs
            WHERE task_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        return _row_to_run(row) if row else None

    def get_latest_session_id(
        self,
        *,
        task_id: str,
        role_id: str,
        agent_backend: str,
    ) -> str | None:
        """Return the latest persisted non-empty session id for one task role backend scope."""

        row = self._connection.execute(
            """
            SELECT session_id FROM runs
            WHERE task_id = ?
              AND role_id = ?
              AND agent_backend = ?
              AND session_id IS NOT NULL
              AND session_id != ''
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (task_id, role_id, agent_backend),
        ).fetchone()
        if row is None:
            return None
        session_id = row["session_id"]
        return str(session_id) if session_id else None

    @retried_on_lock
    def prune_old_runs(
        self,
        *,
        project_id: str,
        older_than: str,
    ) -> int:
        """Delete terminal runs older than one cutoff and their dependent events.

        Runs whose task is still blocked or in_progress are preserved regardless
        of age.  Events attached to the deleted runs are removed first to satisfy
        the foreign-key constraint on events.run_id.  Both deletes execute inside
        a single transaction.

        Returns the number of run rows deleted.
        """

        qualifying_sql = """
            SELECT id FROM runs
            WHERE project_id = ?
              AND completed_at < ?
              AND status IN ({statuses})
              AND NOT EXISTS (
                  SELECT 1 FROM tasks
                  WHERE tasks.id = runs.task_id
                    AND tasks.status IN ({protected})
              )
        """.format(
            statuses=", ".join("?" for _ in self._PRUNE_TERMINAL_RUN_STATUSES),
            protected=", ".join("?" for _ in _PRUNE_PROTECTED_TASK_STATUSES),
        )
        qualifying_params = (
            project_id,
            older_than,
            *self._PRUNE_TERMINAL_RUN_STATUSES,
            *_PRUNE_PROTECTED_TASK_STATUSES,
        )

        with self._connection:
            self._connection.execute(
                f"DELETE FROM events WHERE run_id IN ({qualifying_sql})",
                qualifying_params,
            )
            # Gate decisions are audit records: keep them, drop the run link.
            self._connection.execute(
                f"UPDATE human_gate_decisions SET run_id = NULL"
                f" WHERE run_id IN ({qualifying_sql})",
                qualifying_params,
            )
            cursor = self._connection.execute(
                f"DELETE FROM runs WHERE id IN ({qualifying_sql})",
                qualifying_params,
            )
        return int(cursor.rowcount)

    @retried_on_lock
    def strip_old_run_prompts(
        self,
        *,
        project_id: str,
        older_than: str,
    ) -> int:
        """Null out prompt_text on terminal runs older than one cutoff.

        The run record, telemetry, and status are preserved; only the stored
        prompt text is removed to reduce storage.  Active-work protection is not
        applied here because stripping text from a run record is non-destructive.

        Returns the number of run rows updated.
        """

        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE runs
                SET prompt_text = NULL
                WHERE project_id = ?
                  AND completed_at < ?
                  AND prompt_text IS NOT NULL
                  AND status IN ({statuses})
                """.format(
                    statuses=", ".join("?" for _ in self._PRUNE_TERMINAL_RUN_STATUSES)
                ),
                (
                    project_id,
                    older_than,
                    *self._PRUNE_TERMINAL_RUN_STATUSES,
                ),
            )
        return int(cursor.rowcount)

    def run_totals(
        self,
        *,
        project_id: str | None = None,
        sprint_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, int | float]:
        """Return aggregate run metrics for a project, sprint, or task scope."""

        filters: list[str] = []
        params: list[Any] = []
        join_clause = ""

        if sprint_id is not None:
            join_clause = " JOIN tasks ON tasks.id = runs.task_id"
            filters.append("tasks.sprint_id = ?")
            params.append(sprint_id)
        if project_id is not None:
            filters.append("runs.project_id = ?")
            params.append(project_id)
        if task_id is not None:
            filters.append("runs.task_id = ?")
            params.append(task_id)

        sql = """
            SELECT
                COUNT(runs.id) AS run_count,
                COALESCE(SUM(runs.cost_usd), 0.0) AS total_cost_usd,
                COALESCE(SUM(runs.token_count), 0) AS total_token_count,
                COALESCE(SUM(runs.input_tokens), 0) AS input_tokens,
                COALESCE(SUM(runs.output_tokens), 0) AS output_tokens,
                COALESCE(SUM(runs.cache_read_tokens), 0) AS cache_read_tokens,
                COALESCE(SUM(runs.cache_creation_tokens), 0) AS cache_creation_tokens,
                COALESCE(SUM(runs.duration_ms), 0) AS total_duration_ms,
                COALESCE(
                    SUM(
                        CASE
                            WHEN runs.token_count > 0 AND runs.cost_usd = 0 THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS zero_cost_token_runs
            FROM runs
        """
        sql = f"{sql}{join_clause}"
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"

        row = self._connection.execute(sql, tuple(params)).fetchone()
        assert row is not None
        return {
            "run_count": int(row["run_count"]),
            "total_cost_usd": float(row["total_cost_usd"]),
            "total_token_count": int(row["total_token_count"]),
            "token_usage": _token_usage_from_row(row),
            "total_duration_ms": int(row["total_duration_ms"]),
            "zero_cost_token_runs": int(row["zero_cost_token_runs"]),
        }

    def task_run_totals(
        self,
        *,
        project_id: str | None = None,
        sprint_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return per-task aggregate run metrics for one project or sprint."""

        filters: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            filters.append("tasks.project_id = ?")
            params.append(project_id)
        if sprint_id is not None:
            filters.append("tasks.sprint_id = ?")
            params.append(sprint_id)

        sql = """
            SELECT
                tasks.id AS task_id,
                tasks.title AS task_title,
                tasks.status AS task_status,
                tasks.task_type AS task_type,
                tasks.branch_name AS branch_name,
                tasks.assigned_role AS assigned_role,
                COUNT(runs.id) AS run_count,
                COALESCE(SUM(runs.cost_usd), 0.0) AS total_cost_usd,
                COALESCE(SUM(runs.token_count), 0) AS total_token_count,
                COALESCE(SUM(runs.input_tokens), 0) AS input_tokens,
                COALESCE(SUM(runs.output_tokens), 0) AS output_tokens,
                COALESCE(SUM(runs.cache_read_tokens), 0) AS cache_read_tokens,
                COALESCE(SUM(runs.cache_creation_tokens), 0) AS cache_creation_tokens,
                COALESCE(SUM(runs.duration_ms), 0) AS total_duration_ms
            FROM tasks
            LEFT JOIN runs ON runs.task_id = tasks.id
        """
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"""
            {sql}
            GROUP BY
                tasks.id,
                tasks.title,
                tasks.status,
                tasks.task_type,
                tasks.branch_name,
                tasks.assigned_role
            ORDER BY tasks.priority ASC, tasks.order_index ASC, tasks.created_at ASC, tasks.id ASC
        """

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [
            {
                "task_id": str(row["task_id"]),
                "task_title": str(row["task_title"]),
                "task_status": str(row["task_status"]),
                "task_type": str(row["task_type"]),
                "branch_name": row["branch_name"],
                "assigned_role": row["assigned_role"],
                "run_count": int(row["run_count"]),
                "total_cost_usd": float(row["total_cost_usd"]),
                "total_token_count": int(row["total_token_count"]),
                "token_usage": _token_usage_from_row(row),
                "total_duration_ms": int(row["total_duration_ms"]),
            }
            for row in rows
        ]
