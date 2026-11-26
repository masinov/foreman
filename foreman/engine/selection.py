"""Choosing the task an engine works on next (spec §6.2, ADR-0028)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ..domain.models import Project, Sprint, Task
from ..mutations import MutationError, Mutations
from ..store import ForemanStore
from .errors import OrchestratorError
from ..domain.holds import task_hold
from .holds import sprint_block_over
from .leasing import TaskLeases
from .limits import resolve_project_settings
from .task_writes import TaskWrites

#: The event that records Foreman taking a backlog task into a sprint itself.
PULLED_EVENT = "engine.task_pulled"


def pulled_task_ids(store: ForemanStore, sprint: Sprint) -> list[str]:
    """The tasks Foreman took from the backlog into this sprint on its own, oldest first."""

    seen: list[str] = []
    for event in store.list_events(project_id=sprint.project_id):
        if (
            event.event_type == PULLED_EVENT
            and event.payload.get("sprint_id") == sprint.id
            and event.task_id
            and event.task_id not in seen
        ):
            seen.append(event.task_id)
    return seen


def backlog_ready_for_foreman(store: ForemanStore, project: Project) -> list[Task]:
    """Accepted backlog work Foreman may start, in the order it would take it.

    Higher priority first, then the order it was filed in. A task that waits
    for another is ready only once that one is done.
    """

    backlog = store.get_backlog(project.id)
    if backlog is None:
        return []
    ready = []
    for task in store.list_tasks(sprint_id=backlog.id):
        if task.status != "todo":
            continue
        waits = [store.get_task(dependency) for dependency in task.depends_on_task_ids]
        if any(other is None or other.status != "done" for other in waits):
            continue
        ready.append(task)
    return sorted(ready, key=lambda task: (-task.priority, task.order_index))


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
        """Return the next runnable task for one project.

        What a person planned into the active sprint comes first. A project
        whose ``task_selection_mode`` is ``autonomous`` lets Foreman start
        backlog work on its own: when nothing planned can run, the next
        accepted backlog task is taken into the active sprint, up to
        ``max_autonomous_tasks`` per sprint (ADR-0028).
        """

        selection_mode = resolve_project_settings(project).task_selection_mode
        if selection_mode not in ("directed", "autonomous"):
            raise OrchestratorError(
                f"Task selection mode {selection_mode!r} is not implemented."
            )

        sprint = self.store.get_active_sprint(project.id)
        if sprint is None:
            return None
        # A block on the sprint or the workspace holds all of it (ADR-0043).
        if sprint_block_over(self.store, sprint) is not None:
            return None
        sprint_tasks = self.store.list_tasks(sprint_id=sprint.id)
        tasks_by_id = {task.id: task for task in sprint_tasks}
        # A paused task, or one being blocked, is skipped: the sprint goes on
        # with what does not wait for it (ADR-0043 amends ADR-0039).
        held = {task.id for task in sprint_tasks if task_hold(task) is not None}
        for task in sprint_tasks:
            if task.id in held:
                continue
            if task.status == "in_progress" and task.workflow_current_step:
                # For resumption, try to acquire the lease. If the old holder is
                # still alive (lease not expired), skip this task to avoid stealing
                # work. If the lease has expired, we take it over.
                if self.leases.acquire(task, project) is None:
                    return None  # Another orchestrator holds an active lease.
                return task
        if any(
            task.status == "in_progress"
            and not task.workflow_current_step
            and task.id not in held
            for task in sprint_tasks
        ):
            return None
        for task in sprint_tasks:
            if task.status != "todo" or task.id in held:
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
        if selection_mode == "autonomous":
            return self.pull_from_backlog(project, sprint)
        return None

    def pull_from_backlog(self, project: Project, sprint: Sprint) -> Task | None:
        """Take the next accepted backlog task into the active sprint, if Foreman may.

        The limit per sprint is what bounds an agent filing work that Foreman
        then starts, which files more: each turn of that loop uses one.
        """

        limit = resolve_project_settings(project).max_autonomous_tasks
        if len(pulled_task_ids(self.store, sprint)) >= limit:
            return None
        for candidate in backlog_ready_for_foreman(self.store, project):
            try:
                planned = Mutations(self.store, via="policy", actor="foreman").plan_tasks(
                    [candidate], sprint=sprint, pulled=True
                )
            except MutationError:
                # Someone planned, declined or changed it since it was read.
                continue
            task = planned.tasks[0]
            if self.leases.acquire(task, project) is None:
                return None
            return task
        return None

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
