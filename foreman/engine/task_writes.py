"""How the engine writes a task without overwriting an operator.

The engine and a person can change the same task at the same time. The engine
writes only the columns it owns, never touches a cancelled task, and picks up
what a person changed between steps.
"""

from __future__ import annotations

from ..models import Task
from ..store import ForemanStore
from .errors import OrchestratorError, TaskCancelledError


class TaskWrites:
    """The engine's writes to tasks in one store."""

    def __init__(self, store: ForemanStore) -> None:
        self.store = store

    def save(self, task: Task, *, include_definition: bool = False) -> None:
        """Persist the engine's view of a task without overwriting an operator's.

        Only workflow state is written (see ``update_task_engine_state``). A
        task the store does not know yet is inserted whole. A task an operator
        cancelled is left exactly as it is and ``TaskCancelledError`` stops
        whatever the engine was doing with it.
        """

        written = self.store.update_task_engine_state(
            task, include_definition=include_definition
        )
        if written is None:
            self.store.save_task(task)
        elif written is False:
            raise TaskCancelledError(task.id)

    def adopt_operator_changes(self, task: Task) -> Task:
        """Refresh the fields an operator owns from the store, in place.

        The engine keeps one task object for a whole workflow. Between steps
        it picks up what a person changed (wording, criteria, priority,
        dependencies, overrides) so the next prompt and model choice use it,
        and it returns the stored row so the caller can see a status change.
        """

        fresh = self.store.get_task(task.id)
        if fresh is None:
            raise OrchestratorError(f"Task {task.id!r} disappeared during execution.")
        for name in (
            "title",
            "description",
            "acceptance_criteria",
            "task_type",
            "priority",
            "order_index",
            "depends_on_task_ids",
            "executor_overrides",
            "complexity",
            "sprint_id",
        ):
            setattr(task, name, getattr(fresh, name))
        return fresh
