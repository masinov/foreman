"""Sprints."""

from __future__ import annotations


from ..models import (
    Sprint,
)

from .base import (
    StoreBase,
    retried_on_lock,
)
from .rows import (
    _row_to_sprint,
)


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
                    started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id = excluded.project_id,
                    title = excluded.title,
                    goal = excluded.goal,
                    status = excluded.status,
                    order_index = excluded.order_index,
                    created_at = excluded.created_at,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at
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
        """List all sprints for one project."""

        rows = self._connection.execute(
            """
            SELECT * FROM sprints
            WHERE project_id = ?
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
            WHERE project_id = ? AND status = 'active'
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
            WHERE project_id = ? AND status = 'planned'
            ORDER BY order_index ASC, created_at ASC, id ASC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return _row_to_sprint(row) if row else None

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
            "SELECT COUNT(*) AS value FROM sprints WHERE status = 'active'"
        ).fetchone()
        return int(row["value"])
