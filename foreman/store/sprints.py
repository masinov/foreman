"""Sprints."""

from __future__ import annotations


from typing import Sequence

from ..errors import ForemanError
from ..models import (
    BACKLOG_GOAL,
    BACKLOG_TITLE,
    Sprint,
)

from .base import (
    StoreBase,
    retried_on_lock,
)
from .rows import (
    _row_to_sprint,
)


class StaleTaskError(ForemanError):
    """A task changed between being read and being moved; nothing was moved."""

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task {task_id} changed while it was being moved; nothing was moved.")
        self.task_id = task_id


class SprintStore(StoreBase):
    """Sprints."""

    @retried_on_lock
    def save_sprint(self, sprint: Sprint) -> Sprint:
        """Insert or update a sprint record."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO sprints (
                    id, project_id, title, goal, status, order_index, created_at,
                    started_at, completed_at, kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id = excluded.project_id,
                    title = excluded.title,
                    goal = excluded.goal,
                    status = excluded.status,
                    order_index = excluded.order_index,
                    created_at = excluded.created_at,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    kind = excluded.kind
                """,
                (
                    sprint.id,
                    sprint.project_id,
                    sprint.title,
                    sprint.goal,
                    sprint.status,
                    sprint.order_index,
                    sprint.created_at,
                    sprint.started_at,
                    sprint.completed_at,
                    sprint.kind,
                ),
            )
        return sprint

    def get_sprint(self, sprint_id: str) -> Sprint | None:
        """Return one sprint by identifier."""

        row = self._connection.execute(
            "SELECT * FROM sprints WHERE id = ?",
            (sprint_id,),
        ).fetchone()
        return _row_to_sprint(row) if row else None

    def list_sprints(self, project_id: str) -> list[Sprint]:
        """List all sprints for one project. The backlog is not a sprint."""

        rows = self._connection.execute(
            """
            SELECT * FROM sprints
            WHERE project_id = ? AND kind = 'sprint'
            ORDER BY order_index ASC, created_at ASC, id ASC
            """,
            (project_id,),
        ).fetchall()
        return [_row_to_sprint(row) for row in rows]

    def get_active_sprint(self, project_id: str) -> Sprint | None:
        """Return the active sprint for one project, if it exists."""

        row = self._connection.execute(
            """
            SELECT * FROM sprints
            WHERE project_id = ? AND status = 'active' AND kind = 'sprint'
            ORDER BY started_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return _row_to_sprint(row) if row else None

    def get_next_planned_sprint(self, project_id: str) -> Sprint | None:
        """Return the first planned sprint by queue order, or None."""

        row = self._connection.execute(
            """
            SELECT * FROM sprints
            WHERE project_id = ? AND status = 'planned' AND kind = 'sprint'
            ORDER BY order_index ASC, created_at ASC, id ASC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return _row_to_sprint(row) if row else None

    def get_backlog(self, project_id: str) -> Sprint | None:
        """Return the project's backlog row, or None before anything was filed."""

        row = self._connection.execute(
            "SELECT * FROM sprints WHERE project_id = ? AND kind = 'backlog'",
            (project_id,),
        ).fetchone()
        return _row_to_sprint(row) if row else None

    @retried_on_lock
    def ensure_backlog(self, project_id: str, *, created_at: str) -> Sprint:
        """Return the project's backlog, creating it on first use.

        Its id is ``<project>-backlog``; a project that somehow already has a
        sprint with that id gets a numbered one. The unique index on backlogs
        makes a concurrent first use converge on one row.
        """

        with self._connection:
            row = self._connection.execute(
                "SELECT * FROM sprints WHERE project_id = ? AND kind = 'backlog'",
                (project_id,),
            ).fetchone()
            if row is not None:
                return _row_to_sprint(row)
            backlog_id = f"{project_id}-backlog"
            suffix = 2
            while self._connection.execute(
                "SELECT 1 FROM sprints WHERE id = ?", (backlog_id,)
            ).fetchone():
                backlog_id = f"{project_id}-backlog-{suffix}"
                suffix += 1
            self._connection.execute(
                """
                INSERT INTO sprints (
                    id, project_id, title, goal, status, order_index, created_at, kind
                ) VALUES (?, ?, ?, ?, 'planned', 0, ?, 'backlog')
                ON CONFLICT DO NOTHING
                """,
                (backlog_id, project_id, BACKLOG_TITLE, BACKLOG_GOAL, created_at),
            )
            row = self._connection.execute(
                "SELECT * FROM sprints WHERE project_id = ? AND kind = 'backlog'",
                (project_id,),
            ).fetchone()
        return _row_to_sprint(row)

    @retried_on_lock
    def move_tasks_to_sprint(
        self,
        task_ids: Sequence[str],
        *,
        from_sprint_id: str,
        from_statuses: Sequence[str],
        to_sprint_id: str,
        new_sprint: Sprint | None = None,
    ) -> None:
        """Move tasks between sprints in one transaction, all or none.

        ``new_sprint`` is inserted first, in the same transaction, when the
        destination is created by this move. Each task must still be in
        ``from_sprint_id`` with a status in ``from_statuses`` when the write
        happens; if any is not (someone changed it since it was read),
        nothing is written and ``StaleTaskError`` names it. Tasks go to the
        end of the destination, in the order given.
        """

        status_marks = ", ".join("?" for _ in from_statuses)
        with self._connection:
            if new_sprint is not None:
                self._connection.execute(
                    """
                    INSERT INTO sprints (
                        id, project_id, title, goal, status, order_index, created_at,
                        started_at, completed_at, kind
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_sprint.id,
                        new_sprint.project_id,
                        new_sprint.title,
                        new_sprint.goal,
                        new_sprint.status,
                        new_sprint.order_index,
                        new_sprint.created_at,
                        new_sprint.started_at,
                        new_sprint.completed_at,
                        new_sprint.kind,
                    ),
                )
            row = self._connection.execute(
                "SELECT MAX(order_index) AS top FROM tasks WHERE sprint_id = ?",
                (to_sprint_id,),
            ).fetchone()
            next_index = (row["top"] if row["top"] is not None else -1) + 1
            for task_id in task_ids:
                cursor = self._connection.execute(
                    f"""
                    UPDATE tasks SET sprint_id = ?, order_index = ?
                    WHERE id = ? AND sprint_id = ? AND status IN ({status_marks})
                    """,
                    (to_sprint_id, next_index, task_id, from_sprint_id, *from_statuses),
                )
                if cursor.rowcount != 1:
                    raise StaleTaskError(task_id)
                next_index += 1

    @retried_on_lock
    def delete_sprint(self, sprint_id: str) -> dict[str, str]:
        """Delete a sprint and everything that hangs off it, in one transaction."""

        with self._connection:
            self._delete_task_dependents(
                self._connection,
                "SELECT id FROM tasks WHERE sprint_id = ?",
                (sprint_id,),
            )
            self._connection.execute("DELETE FROM tasks WHERE sprint_id = ?", (sprint_id,))
            self._connection.execute(
                "DELETE FROM decision_gates WHERE sprint_id = ?", (sprint_id,)
            )
            self._connection.execute("DELETE FROM sprints WHERE id = ?", (sprint_id,))
        return {"ok": "deleted"}

    def count_active_sprints(self) -> int:
        """Return the number of active sprints across all projects."""

        row = self._connection.execute(
            "SELECT COUNT(*) AS value FROM sprints WHERE status = 'active' AND kind = 'sprint'"
        ).fetchone()
        return int(row["value"])
