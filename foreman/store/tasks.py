"""Tasks, their keys and their dependents."""

from __future__ import annotations

import sqlite3
from typing import Any, Sequence

from ..models import (
    TASK_STATUSES,
    Task,
)

from .base import (
    StoreBase,
    retried_on_lock,
)
from .rows import (
    _json_dumps,
    _row_to_task,
    _serialize_evidence,
    derive_task_key_prefix,
)


class TaskStore(StoreBase):
    """Tasks, their keys and their dependents."""

    def update_task_engine_state(
        self, task: Task, *, include_definition: bool = False
    ) -> bool | None:
        """Write only the columns the engine owns for an existing task.

        ``save_task`` replaces the whole row, so an engine holding a task
        object for the length of a workflow overwrote whatever an operator
        changed in the meantime: an edited title or criteria, a changed
        priority or override, and a cancellation, after which the cancelled
        task was merged and marked done.

        This writes workflow state only (status, block reason, branch,
        worktree, role, step, carried output, visit counts, evidence, start
        and completion times) and never touches a row whose status is
        ``cancelled``: cancellation is an operator's terminal decision.
        ``include_definition`` adds title, type and acceptance criteria, for
        the autonomous flow in which the agent names the task it picked.

        Returns True when written, False when the task is cancelled (the row
        is left alone), and None when no such task exists.
        """

        assignments = [
            "status = ?",
            "blocked_reason = ?",
            "branch_name = ?",
            "worktree_path = ?",
            "assigned_role = ?",
            "workflow_current_step = ?",
            "workflow_carried_output = ?",
            "step_visit_counts = ?",
            "completion_evidence_json = ?",
            "started_at = ?",
            "completed_at = ?",
        ]
        values: list[Any] = [
            task.status,
            task.blocked_reason,
            task.branch_name,
            getattr(task, "worktree_path", None),
            task.assigned_role,
            task.workflow_current_step,
            task.workflow_carried_output,
            _json_dumps(task.step_visit_counts),
            _serialize_evidence(getattr(task, "completion_evidence", None)),
            task.started_at,
            task.completed_at,
        ]
        if include_definition:
            assignments += ["title = ?", "task_type = ?", "acceptance_criteria = ?"]
            values += [task.title, task.task_type, task.acceptance_criteria]

        def _write(connection: sqlite3.Connection) -> int:
            cursor = connection.execute(
                f"UPDATE tasks SET {', '.join(assignments)} "
                "WHERE id = ? AND status != 'cancelled'",
                (*values, task.id),
            )
            return cursor.rowcount

        if self._write(_write) > 0:
            return True
        return False if self.get_task(task.id) is not None else None

    def save_task(self, task: Task) -> Task:
        """Insert or update a task record.

        Assigns a Jira-style ``task_key`` (e.g. ``FOR-102``) to brand-new tasks.
        The key is write-once: it is set on INSERT and never changed by updates.
        """

        is_new = not task.task_key and self.get_task(task.id) is None

        def _write_task(connection: sqlite3.Connection) -> str:
            # Allocate inside the transaction so the sequence bump and the
            # INSERT commit together; a rolled-back attempt leaves no gap.
            task_key = task.task_key or (self._next_task_key(task.project_id) if is_new else "")
            connection.execute(
                """
                INSERT INTO tasks (
                    id, sprint_id, project_id, title, task_key, description, status, task_type,
                    priority, order_index, branch_name, worktree_path, assigned_role,
                    acceptance_criteria, blocked_reason, created_by,
                    depends_on_task_ids, workflow_current_step,
                    workflow_carried_output, step_visit_counts, completion_evidence_json,
                    executor_overrides_json, complexity,
                    source_system, source_ref, source_url, reporter,
                    created_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    sprint_id = excluded.sprint_id,
                    project_id = excluded.project_id,
                    title = excluded.title,
                    description = excluded.description,
                    status = excluded.status,
                    task_type = excluded.task_type,
                    priority = excluded.priority,
                    order_index = excluded.order_index,
                    branch_name = excluded.branch_name,
                    worktree_path = excluded.worktree_path,
                    assigned_role = excluded.assigned_role,
                    acceptance_criteria = excluded.acceptance_criteria,
                    blocked_reason = excluded.blocked_reason,
                    created_by = excluded.created_by,
                    depends_on_task_ids = excluded.depends_on_task_ids,
                    workflow_current_step = excluded.workflow_current_step,
                    workflow_carried_output = excluded.workflow_carried_output,
                    step_visit_counts = excluded.step_visit_counts,
                    completion_evidence_json = excluded.completion_evidence_json,
                    executor_overrides_json = excluded.executor_overrides_json,
                    complexity = excluded.complexity,
                    source_system = excluded.source_system,
                    source_ref = excluded.source_ref,
                    source_url = excluded.source_url,
                    reporter = excluded.reporter,
                    created_at = excluded.created_at,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at
                """,
                (
                    task.id,
                    task.sprint_id,
                    task.project_id,
                    task.title,
                    task_key,
                    task.description,
                    task.status,
                    task.task_type,
                    task.priority,
                    task.order_index,
                    task.branch_name,
                    getattr(task, "worktree_path", None),
                    task.assigned_role,
                    task.acceptance_criteria,
                    task.blocked_reason,
                    task.created_by,
                    _json_dumps(task.depends_on_task_ids),
                    task.workflow_current_step,
                    task.workflow_carried_output,
                    _json_dumps(task.step_visit_counts),
                    _serialize_evidence(getattr(task, "completion_evidence", None)),
                    _json_dumps(getattr(task, "executor_overrides", {}) or {}),
                    getattr(task, "complexity", None),
                    getattr(task, "source_system", None),
                    getattr(task, "source_ref", None),
                    getattr(task, "source_url", None),
                    getattr(task, "reporter", None),
                    task.created_at,
                    task.started_at,
                    task.completed_at,
                ),
            )
            return task_key

        task.task_key = self._write(_write_task)
        return task

    def _ensure_project_key_prefix(self, project_id: str) -> str:
        """Return the project's task-key prefix, deriving and persisting one if unset."""

        row = self._connection.execute(
            "SELECT name, task_key_prefix FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return "TASK"
        prefix = (row["task_key_prefix"] or "").strip()
        if prefix:
            return prefix
        prefix = derive_task_key_prefix(row["name"])
        self._connection.execute(
            "UPDATE projects SET task_key_prefix = ? WHERE id = ?",
            (prefix, project_id),
        )
        return prefix

    def _next_task_key(self, project_id: str) -> str:
        """Allocate the next ``PREFIX-N`` key from the project's sequence.

        Must be called inside the caller's write transaction. The ``UPDATE``
        takes the database write lock, so concurrent writers serialize on the
        sequence and can never mint the same key. Keys that already exist
        (explicitly assigned rows) are skipped.
        """

        prefix = self._ensure_project_key_prefix(project_id)
        while True:
            self._connection.execute(
                "UPDATE projects SET task_key_seq = task_key_seq + 1 WHERE id = ?",
                (project_id,),
            )
            row = self._connection.execute(
                "SELECT task_key_seq FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if row is None:
                return f"{prefix}-1"
            candidate = f"{prefix}-{int(row['task_key_seq'])}"
            taken = self._connection.execute(
                "SELECT 1 FROM tasks WHERE project_id = ? AND task_key = ? LIMIT 1",
                (project_id, candidate),
            ).fetchone()
            if taken is None:
                return candidate

    @retried_on_lock
    def _backfill_task_keys(self) -> None:
        """Assign keys to any pre-existing keyless tasks (one-time, idempotent)."""

        missing = self._connection.execute(
            "SELECT 1 FROM tasks WHERE task_key = '' LIMIT 1"
        ).fetchone()
        if missing is None:
            return
        with self._connection:
            project_ids = [
                row["id"] for row in self._connection.execute("SELECT id FROM projects")
            ]
            for project_id in project_ids:
                keyless = self._connection.execute(
                    "SELECT id FROM tasks WHERE project_id = ? AND task_key = '' "
                    "ORDER BY created_at, id",
                    (project_id,),
                ).fetchall()
                for row in keyless:
                    self._connection.execute(
                        "UPDATE tasks SET task_key = ? WHERE id = ?",
                        (self._next_task_key(project_id), row["id"]),
                    )

    def get_task(self, task_id: str) -> Task | None:
        """Return one task by identifier."""

        row = self._connection.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return _row_to_task(row) if row else None

    def list_tasks(
        self,
        *,
        project_id: str | None = None,
        sprint_id: str | None = None,
        status: str | None = None,
        statuses: Sequence[str] | None = None,
    ) -> list[Task]:
        """List tasks filtered by project and or sprint."""

        filters: list[str] = []
        params: list[Any] = []
        if status is not None and statuses is not None:
            raise ValueError("Provide either status or statuses, not both.")
        if project_id is not None:
            filters.append("project_id = ?")
            params.append(project_id)
        if sprint_id is not None:
            filters.append("sprint_id = ?")
            params.append(sprint_id)
        if status is not None:
            statuses = (status,)
        if statuses is not None:
            placeholders = ", ".join("?" for _ in statuses)
            filters.append(f"status IN ({placeholders})")
            params.extend(statuses)

        sql = "SELECT * FROM tasks"
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"{sql} ORDER BY priority ASC, order_index ASC, created_at ASC, id ASC"

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_task(row) for row in rows]

    def next_task_order_index(self, sprint_id: str) -> int:
        """Return the next order_index for a task in a sprint (max + 1)."""
        row = self._connection.execute(
            """
            SELECT MAX(order_index) AS max_idx FROM tasks WHERE sprint_id = ?
            """,
            (sprint_id,),
        ).fetchone()
        max_idx = row["max_idx"] if row and row["max_idx"] is not None else -1
        return max_idx + 1

    def find_task_by_branch(
        self,
        *,
        project_id: str,
        branch_name: str,
    ) -> Task | None:
        """Return the best task match for one persisted branch name."""

        row = self._connection.execute(
            """
            SELECT * FROM tasks
            WHERE project_id = ? AND branch_name = ?
            ORDER BY
                CASE status
                    WHEN 'in_progress' THEN 0
                    WHEN 'blocked' THEN 1
                    WHEN 'todo' THEN 2
                    WHEN 'triage' THEN 3
                    WHEN 'done' THEN 4
                    WHEN 'cancelled' THEN 5
                    ELSE 6
                END,
                created_at DESC,
                id DESC
            LIMIT 1
            """,
            (project_id, branch_name),
        ).fetchone()
        return _row_to_task(row) if row else None

    @retried_on_lock
    def delete_task(self, task_id: str) -> dict[str, str]:
        """Delete a task and everything that hangs off it, in one transaction."""

        with self._connection:
            self._delete_task_dependents(self._connection, "SELECT ? AS id", (task_id,))
            self._connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return {"ok": "deleted"}

    @staticmethod
    def _delete_task_dependents(
        connection: sqlite3.Connection,
        task_ids_sql: str,
        params: tuple[Any, ...],
    ) -> None:
        """Delete rows that reference the tasks selected by ``task_ids_sql``.

        Covers events, runs, human gate decisions, merge waivers, and task
        leases. Ordered so every foreign key is satisfied even on databases
        whose gate tables predate the ON DELETE rules from migration 14.
        """

        connection.execute(
            f"DELETE FROM events WHERE task_id IN ({task_ids_sql})"
            f" OR run_id IN (SELECT id FROM runs WHERE task_id IN ({task_ids_sql}))",
            (*params, *params),
        )
        connection.execute(
            f"DELETE FROM human_gate_decisions WHERE task_id IN ({task_ids_sql})",
            params,
        )
        connection.execute(
            f"DELETE FROM merge_waivers WHERE task_id IN ({task_ids_sql})",
            params,
        )
        connection.execute(
            f"DELETE FROM leases WHERE resource_type = 'task'"
            f" AND resource_id IN ({task_ids_sql})",
            params,
        )
        connection.execute(
            f"DELETE FROM runs WHERE task_id IN ({task_ids_sql})",
            params,
        )

    def task_counts(
        self,
        project_id: str | None = None,
        sprint_id: str | None = None,
    ) -> dict[str, int]:
        """Return task counts keyed by task status."""

        sql = "SELECT status, COUNT(*) AS value FROM tasks"
        filters: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            filters.append("project_id = ?")
            params.append(project_id)
        if sprint_id is not None:
            filters.append("sprint_id = ?")
            params.append(sprint_id)
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"{sql} GROUP BY status"

        counts = {status: 0 for status in TASK_STATUSES}
        for row in self._connection.execute(sql, tuple(params)).fetchall():
            counts[str(row["status"])] = int(row["value"])
        return counts

    def find_task_by_source(
        self, *, project_id: str, source_system: str, source_ref: str
    ) -> Task | None:
        """Return the task a system already filed under one external reference.

        This is the intake idempotency lookup: the same incident posted twice
        must resolve to the same task rather than a duplicate.
        """

        if not source_system or not source_ref:
            return None
        row = self._connection.execute(
            """
            SELECT * FROM tasks
            WHERE project_id = ? AND source_system = ? AND source_ref = ?
            ORDER BY created_at ASC, rowid ASC
            LIMIT 1
            """,
            (project_id, source_system, source_ref),
        ).fetchone()
        return _row_to_task(row) if row else None
