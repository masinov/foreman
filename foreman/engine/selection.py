"""Choosing the task an engine works on next (spec §6.2)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from uuid import uuid4

from ..models import Project, Task
from ..store import ForemanStore
from .errors import OrchestratorError
from .leasing import TaskLeases
from .limits import resolve_project_settings
from .task_writes import TaskWrites

#: Title of the task the engine creates in autonomous mode for the agent to
#: name. A task that still has it was never named by ``signal.task_started``.
AUTONOMOUS_PLACEHOLDER_TITLE = "[autonomous] new task"


class TaskSelector:
    """Picks, and leases, the next runnable task of a project."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        leases: TaskLeases,
        tasks: TaskWrites,
        block_task_for_error: Callable[..., None],
    ) -> None:
        self.store = store
        self.leases = leases
        self.tasks = tasks
        self.block_task_for_error = block_task_for_error

    def select_next_task(self, project: Project) -> Task | None:
        """Return the next runnable task for one project."""

        selection_mode = resolve_project_settings(project).task_selection_mode
        if selection_mode == "autonomous":
            return self.select_next_task_autonomous(project)
        if selection_mode != "directed":
            raise OrchestratorError(
                f"Task selection mode {selection_mode!r} is not implemented."
            )

        sprint = self.store.get_active_sprint(project.id)
        if sprint is None:
            return None
        sprint_tasks = self.store.list_tasks(sprint_id=sprint.id)
        tasks_by_id = {task.id: task for task in sprint_tasks}
        for task in sprint_tasks:
            if task.status == "in_progress" and task.workflow_current_step:
                # For resumption, try to acquire the lease. If the old holder is
                # still alive (lease not expired), skip this task to avoid stealing
                # work. If the lease has expired, we take it over.
                if self.leases.acquire(task, project) is None:
                    return None  # Another orchestrator holds an active lease.
                return task
        if any(
            task.status == "in_progress" and not task.workflow_current_step
            for task in sprint_tasks
        ):
            return None
        for task in sprint_tasks:
            if task.status != "todo":
                continue
            cancelled = self.cancelled_dependencies(task, tasks_by_id)
            if cancelled:
                # The prerequisite will never be delivered. Running the task
                # anyway would build on work that does not exist; park it for
                # a person to re-plan instead.
                self.block_task_for_error(
                    task.id,
                    "Dependency cancelled: "
                    + ", ".join(cancelled)
                    + ". Re-plan the task, then `foreman task unblock` it or cancel it.",
                    attention_trigger="dependency_cancelled",
                )
                continue
            if not self.dependencies_satisfied(task, tasks_by_id):
                continue
            # Lease the task before returning it. If denied, another
            # orchestrator holds it — skip to the next candidate.
            if self.leases.acquire(task, project) is None:
                continue
            return task
        return None

    def select_next_task_autonomous(self, project: Project) -> Task | None:
        """Select the next task in autonomous mode.

        Resumes an in-progress task if one exists.  Otherwise creates a new
        placeholder task for the agent to populate via ``signal.task_started``.
        Returns ``None`` when there is no active sprint or the autonomous task
        limit for this sprint has been reached.
        """
        sprint = self.store.get_active_sprint(project.id)
        if sprint is None:
            return None

        sprint_tasks = self.store.list_tasks(sprint_id=sprint.id)

        # Resume an in-progress task that has a persisted workflow position.
        for task in sprint_tasks:
            if task.status == "in_progress" and task.workflow_current_step:
                # For resumption, try to acquire the lease. If the old holder is
                # still alive (lease not expired), skip this task to avoid
                # stealing work. If the lease has expired, we take it over.
                if self.leases.acquire(task, project) is None:
                    return None  # Another orchestrator holds an active lease.
                return task
        if any(
            task.status == "in_progress" and not task.workflow_current_step
            for task in sprint_tasks
        ):
            return None

        # Check the per-sprint autonomous task limit.
        max_tasks = resolve_project_settings(project).max_autonomous_tasks
        orchestrator_tasks = [t for t in sprint_tasks if t.created_by == "orchestrator"]
        if len(orchestrator_tasks) >= max_tasks:
            return None

        # Create a new placeholder task for the agent to populate.
        placeholder = Task(
            id=str(uuid4()),
            sprint_id=sprint.id,
            project_id=project.id,
            title=AUTONOMOUS_PLACEHOLDER_TITLE,
            status="todo",
            created_by="orchestrator",
        )
        self.tasks.save(placeholder)
        # Acquire lease for the new placeholder immediately.
        if self.leases.acquire(placeholder, project) is None:
            # Race: another orchestrator created one first; reload and return it.
            sprint_tasks = self.store.list_tasks(sprint_id=sprint.id)
            for task in sprint_tasks:
                if task.status == "in_progress" and task.workflow_current_step:
                    return task
            return None
        return placeholder

    def dependencies_satisfied(
        self,
        task: Task,
        tasks_by_id: Mapping[str, Task],
    ) -> bool:
        for dependency_id in task.depends_on_task_ids:
            dependency = tasks_by_id.get(dependency_id) or self.store.get_task(dependency_id)
            if dependency is None:
                return False
            # Only a delivered dependency satisfies. A cancelled one is a
            # planning decision the dependent task must be re-planned around;
            # ``cancelled_dependencies`` turns it into a block with attention.
            if dependency.status != "done":
                return False
        return True

    def cancelled_dependencies(
        self,
        task: Task,
        tasks_by_id: Mapping[str, Task],
    ) -> list[str]:
        cancelled: list[str] = []
        for dependency_id in task.depends_on_task_ids:
            dependency = tasks_by_id.get(dependency_id) or self.store.get_task(dependency_id)
            if dependency is not None and dependency.status == "cancelled":
                cancelled.append(dependency.id)
        return cancelled
