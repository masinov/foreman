"""The records outcome numbers are computed from (ADR-0034).

One read per kind, scoped to a project or one of its sprints: the tasks,
their runs, and only the events ``foreman.domain.outcome_numbers`` uses, so
an agent's raw output is never loaded for it.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..domain.models import Event, Run, Task
from ..domain.outcome_numbers import OUTCOME_EVENT_TYPES
from .base import StoreBase
from .rows import _row_to_event, _row_to_run, _row_to_task


class OutcomeStore(StoreBase):
    """Reads for the outcome numbers of a project or a sprint."""

    def outcome_records(
        self, project_id: str, *, sprint_id: str | None = None
    ) -> tuple[list[Task], list[Run], list[Event]]:
        """The tasks of *project_id* (or of *sprint_id*), their runs and their outcome events."""

        scope = "tasks.project_id = ?"
        params: list[Any] = [project_id]
        if sprint_id is not None:
            scope += " AND tasks.sprint_id = ?"
            params.append(sprint_id)
        return self._outcome_records(scope, params)

    def outcome_records_for_tasks(
        self, task_ids: Sequence[str]
    ) -> tuple[list[Task], list[Run], list[Event]]:
        """These tasks, their runs and their outcome events."""

        if not task_ids:
            return [], [], []
        scope = f"tasks.id IN ({', '.join('?' for _ in task_ids)})"
        return self._outcome_records(scope, list(task_ids))

    def _outcome_records(
        self, scope: str, params: list[Any]
    ) -> tuple[list[Task], list[Run], list[Event]]:
        connection = self._connection
        tasks = [
            _row_to_task(row)
            for row in connection.execute(
                f"SELECT tasks.* FROM tasks WHERE {scope} ORDER BY tasks.created_at, tasks.id",
                params,
            )
        ]
        runs = [
            _row_to_run(row)
            for row in connection.execute(
                f"""
                SELECT runs.* FROM runs JOIN tasks ON tasks.id = runs.task_id
                WHERE {scope}
                ORDER BY runs.created_at, runs.id
                """,
                params,
            )
        ]
        placeholders = ", ".join("?" for _ in OUTCOME_EVENT_TYPES)
        events = [
            _row_to_event(row)
            for row in connection.execute(
                f"""
                SELECT e.* FROM events e JOIN tasks ON tasks.id = e.task_id
                WHERE {scope} AND e.event_type IN ({placeholders})
                ORDER BY e.timestamp, e.rowid
                """,
                [*params, *OUTCOME_EVENT_TYPES],
            )
        ]
        return tasks, runs, events
