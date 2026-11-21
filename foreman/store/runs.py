"""Runs, their totals and their retention."""

from __future__ import annotations

import sqlite3
from typing import Any, Sequence

from ..domain.activity import WhoRule

from ..domain.models import (
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
                    input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
                    commit_sha, session_cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    cache_creation_tokens = excluded.cache_creation_tokens,
                    commit_sha = excluded.commit_sha,
                    session_cost_usd = excluded.session_cost_usd
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
                    run.commit_sha,
                    run.session_cost_usd,
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

    def list_task_runs_page(
        self, task_id: str, *, limit: int, offset: int
    ) -> tuple[list[Run], int]:
        """Return one page of a task's runs, newest first, and the total count."""

        total = self._connection.execute(
            "SELECT COUNT(*) FROM runs WHERE task_id = ?", (task_id,)
        ).fetchone()[0]
        rows = self._connection.execute(
            """
            SELECT * FROM runs WHERE task_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT ? OFFSET ?
            """,
            (task_id, limit, offset),
        ).fetchall()
        return [_row_to_run(row) for row in rows], int(total)

    def list_sprint_activity_page(
        self,
        sprint_id: str,
        *,
        limit: int,
        offset: int,
        skip_roles: Sequence[str],
        skip_steps: Sequence[str],
        skip_outcomes: Sequence[str],
        gate_role: str,
        hand_events: dict[str, str],
        who: WhoRule,
        problem_outcomes: Sequence[str] | None = None,
        problem_statuses: Sequence[str] = (),
        by: str | None = None,
    ) -> tuple[list[dict[str, Any]], int, list[str]]:
        """One page of a sprint's activity, newest first, the total, and who appears in it.

        Runs of the sprint's tasks, less those of ``skip_roles``, at
        ``skip_steps``, with ``skip_outcomes``, and gate runs no person
        decided; with the events ``hand_events`` names (event type to the
        outcome it is listed as), whose ``by`` is the actor and ``reason`` the
        detail. With ``problem_outcomes`` only those outcomes, or runs with
        one of ``problem_statuses``, are kept. Each row's ``who`` is
        ``who.user`` for what a person did, ``who.foreman`` for the engine's
        own steps, else the run's role; with ``by`` only rows of that ``who``
        are kept. The last value lists every ``who`` in the sprint's activity,
        whatever the filters. ``foreman.domain.activity`` says what goes in each.
        """

        def marks(values: Sequence[str]) -> str:
            return ", ".join("?" for _ in values) or "NULL"

        hand_types = list(hand_events)
        rows_sql = f"""
            SELECT 'run' AS source, r.id AS id, r.task_id AS task_id,
                   COALESCE(r.started_at, r.created_at) AS at,
                   r.workflow_step AS step, r.role_id AS role_id,
                   r.agent_backend AS backend, r.model AS model, r.status AS status,
                   r.outcome AS outcome, r.outcome_detail AS outcome_detail,
                   r.commit_sha AS commit_sha, r.duration_ms AS duration_ms,
                   r.cost_usd AS cost_usd, NULL AS actor,
                   CASE WHEN r.agent_backend IN ({marks(who.user_backends)})
                             OR r.role_id IN ({marks(who.user_roles)}) THEN ?
                        WHEN r.agent_backend IN ({marks(who.engine_backends)})
                             OR substr(r.role_id, 1, ?) = ? THEN ?
                        ELSE r.role_id END AS who
            FROM runs r JOIN tasks t ON t.id = r.task_id
            WHERE t.sprint_id = ?
              AND r.role_id NOT IN ({marks(skip_roles)})
              AND r.workflow_step NOT IN ({marks(skip_steps)})
              AND COALESCE(r.outcome, '') NOT IN ({marks(skip_outcomes)})
              AND NOT (r.role_id = ? AND r.agent_backend <> 'human')
            UNION ALL
            SELECT 'event', e.id, e.task_id, e.timestamp, NULL, 'human', 'human', NULL,
                   'completed',
                   CASE e.event_type {" ".join("WHEN ? THEN ?" for _ in hand_types)} END,
                   json_extract(e.payload_json, '$.reason'), NULL, NULL, 0,
                   json_extract(e.payload_json, '$.by'), ?
            FROM events e JOIN tasks t ON t.id = e.task_id
            WHERE t.sprint_id = ? AND e.event_type IN ({marks(hand_types)})
        """
        params: list[Any] = [
            *who.user_backends, *who.user_roles, who.user,
            *who.engine_backends, len(who.builtin_prefix), who.builtin_prefix, who.foreman,
            sprint_id, *skip_roles, *skip_steps, *skip_outcomes, gate_role,
        ]
        for event_type in hand_types:
            params.extend([event_type, hand_events[event_type]])
        params.extend([who.user, sprint_id, *hand_types])
        present = [
            row[0]
            for row in self._connection.execute(
                f"SELECT DISTINCT a.who FROM ({rows_sql}) a ORDER BY a.who", params
            ).fetchall()
            if row[0]
        ]
        conditions: list[str] = []
        all_params = list(params)
        if problem_outcomes is not None:
            conditions.append(
                f"(COALESCE(a.outcome, '') IN ({marks(problem_outcomes)})"
                f" OR a.status IN ({marks(problem_statuses)}))"
            )
            all_params.extend([*problem_outcomes, *problem_statuses])
        if by:
            conditions.append("a.who = ?")
            all_params.append(by)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params = all_params
        total = self._connection.execute(
            f"SELECT COUNT(*) FROM ({rows_sql}) a {where}", params
        ).fetchone()[0]
        rows = self._connection.execute(
            f"SELECT a.* FROM ({rows_sql}) a {where}"
            " ORDER BY julianday(a.at) DESC, a.id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [dict(row) for row in rows], int(total), present

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

    def latest_session_cost(self, *, session_id: str, agent_backend: str) -> float:
        """Return the backend's last reported running total for a session.

        Zero when no finished run of that session recorded one.
        """

        row = self._connection.execute(
            """
            SELECT session_cost_usd FROM runs
            WHERE session_id = ?
              AND agent_backend = ?
              AND session_cost_usd IS NOT NULL
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (session_id, agent_backend),
        ).fetchone()
        return float(row["session_cost_usd"]) if row else 0.0

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
