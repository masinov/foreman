"""The backlog (ADR-0021): filing work, declining it, planning it into a
sprint and taking it back out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..domain.models import (
    TASK_COMPLEXITIES,
    TASK_TYPES,
    Project,
    Sprint,
    SprintStatus,
    Task,
)
from ..domain.policy import PolicyDecision, PolicyMatrix
from ..store.sprints import StaleTaskError
from .base import _NOT_STARTED_STATUSES, MutationBase, MutationError, slug_id

#: Sprints backlog work can be planned into.
PLANNABLE_SPRINT_STATUSES: tuple[SprintStatus, ...] = ("planned", "active")


@dataclass(frozen=True)
class FiledTask:
    """A task filed into the backlog, with the triage decision that set its state."""

    task: Task
    triage: PolicyDecision
    accepted_by_filer: bool = False


@dataclass(frozen=True)
class PlannedTasks:
    """Tasks planned into a sprint, and whether the sprint was created for them."""

    sprint: Sprint
    tasks: tuple[Task, ...]
    created_sprint: bool


class BacklogMutations(MutationBase):
    """Filing, declining, planning and unplanning backlog work."""

    def file_task(
        self,
        project: Project,
        *,
        title: str,
        task_type: str = "feature",
        description: str | None = None,
        acceptance_criteria: str | None = None,
        priority: int = 0,
        complexity: str | None = None,
        created_by: str | None = None,
        source: Mapping[str, str | None] | None = None,
        accept: bool = False,
        into: Sprint | None = None,
        event_type: str = "backlog.task_filed",
        step: str = "file",
        event_payload: Mapping[str, Any] | None = None,
    ) -> FiledTask:
        """File one task into the project's backlog.

        The project's triage policy (ADR-0014) decides its state: ``human``
        leaves it filed (``triage``) and raises one attention turn; ``auto``
        accepts it (``todo``). It is never planned. ``accept`` files it
        already accepted, for a person whose filing is the decision.

        ``into`` names a sprint instead of the backlog. Only the intake API
        uses it, because its callers could always name one (ADR-0013).
        ``event_type``, ``step`` and ``event_payload`` let intake keep its
        own audit event; everyone else records ``backlog.task_filed``.
        """

        clean_title = (title or "").strip()
        if not clean_title:
            raise MutationError("Task title is required.")
        if task_type not in TASK_TYPES:
            raise MutationError(
                f"Unsupported task type: {task_type}. Expected one of: {', '.join(TASK_TYPES)}."
            )
        if complexity is not None and complexity not in TASK_COMPLEXITIES:
            raise MutationError(
                f"Unsupported complexity: {complexity}. "
                f"Expected one of: {', '.join(TASK_COMPLEXITIES)}."
            )
        if into is not None and into.project_id != project.id:
            raise MutationError(f"Sprint {into.id} belongs to another project.")

        now = self._now()
        if into is not None and not into.is_backlog:
            target = into
        else:
            target = self.store.ensure_backlog(project.id, created_at=now.isoformat())
        triage = PolicyMatrix.for_project(project).resolve("triage", task_type=task_type)
        # A request is work someone other than a person filed, where the
        # project wants a person to say yes first (ADR-0028). What a person
        # files is that person's decision already.
        filed = triage.value == "human" and not accept and self.role != "human"
        source = dict(source or {})
        task = Task(
            id=slug_id("task", clean_title, self.store.get_task),
            sprint_id=target.id,
            project_id=project.id,
            title=clean_title,
            status="triage" if filed else "todo",
            task_type=task_type,  # type: ignore[arg-type]
            description=(description or "").strip() or None,
            acceptance_criteria=(acceptance_criteria or "").strip() or None,
            complexity=complexity,
            priority=int(priority or 0),
            order_index=self.store.next_task_order_index(target.id),
            created_by=created_by or self.actor or self.role,
            source_system=source.get("system"),
            source_ref=source.get("external_ref"),
            source_url=source.get("url"),
            reporter=source.get("reporter"),
            created_at=now.isoformat(),
        )
        task = self.store.save_task(task)
        event = self._audit(
            task,
            event_type,
            step=step,
            title=task.title,
            task_type=task.task_type,
            sprint_id=target.id,
            created_by=task.created_by,
            status=task.status,
            triage=triage.as_dict(),
            accepted_by_filer=True if triage.value == "human" and not filed else None,
            **dict(event_payload or {}),
        )
        if filed:
            self._attention(task, project, trigger="triage", run_id=event.run_id)
        return FiledTask(task=task, triage=triage, accepted_by_filer=accept)

    def decline_task(self, task: Task, reason: str | None = None) -> Task:
        """Decline filed work. It is kept, marked declined, in the backlog.

        A filed task can be declined wherever it is; an accepted one only
        while it is still in the backlog. Work already planned into a sprint
        has to come back to the backlog first, or be cancelled.
        """

        in_backlog = self._in_backlog(task)
        if task.status == "declined":
            raise MutationError(f"Task {task.id} is already declined.")
        if task.status == "todo" and not in_backlog:
            raise MutationError(
                f"Task {task.id} is already planned into sprint {task.sprint_id}. "
                "Move it back to the backlog first, or cancel it."
            )
        if task.status not in ("triage", "todo"):
            raise MutationError(
                f"Cannot decline a task with status '{task.status}'; only filed or "
                "accepted, unplanned work can be declined."
            )
        self._refuse_if_running(task, "decline")
        from_status = task.status
        from_sprint = task.sprint_id
        if not in_backlog:
            backlog = self.store.ensure_backlog(
                task.project_id, created_at=self._now().isoformat()
            )
            task.sprint_id = backlog.id
            task.order_index = self.store.next_task_order_index(backlog.id)
        task.status = "declined"
        task.completed_at = self._now().isoformat()
        self.store.save_task(task)
        self._audit(
            task,
            "human.task_declined",
            step="decline",
            from_status=from_status,
            from_sprint_id=from_sprint if from_sprint != task.sprint_id else None,
            reason=(reason or "").strip() or None,
        )
        return task

    def plan_tasks(
        self,
        tasks: Sequence[Task],
        *,
        sprint: Sprint | None = None,
        new_sprint_title: str | None = None,
        new_sprint_goal: str | None = None,
        pulled: bool = False,
    ) -> PlannedTasks:
        """Plan backlog tasks into a sprint, all or none.

        The sprint is either ``sprint`` (planned or active) or a new planned
        sprint titled ``new_sprint_title``, created in the same transaction.

        A person may plan a request (a filed task nobody has accepted): putting
        it in a sprint is the yes. Foreman, acting by policy (``via`` is
        ``policy``), may only plan accepted work. ``pulled`` marks the engine
        taking backlog work on its own (ADR-0028): it is recorded as
        ``engine.task_pulled``, which is what the limit per sprint counts.
        """

        title = (new_sprint_title or "").strip()
        if (sprint is None) == (not title):
            raise MutationError("Name a sprint to plan into, or the title of a new one; not both.")
        if not tasks:
            raise MutationError("Name at least one task to plan.")
        project_id = tasks[0].project_id
        seen: set[str] = set()
        for task in tasks:
            if task.id in seen:
                raise MutationError(f"Task {task.id} is named twice.")
            seen.add(task.id)
            if task.project_id != project_id:
                raise MutationError("Every task planned together must belong to one project.")
        backlog = self.store.get_backlog(project_id)
        by_policy = self.via == "policy"
        for task in tasks:
            if backlog is None or task.sprint_id != backlog.id:
                raise MutationError(
                    f"Task {task.id} is not in the backlog (it is in sprint {task.sprint_id})."
                )
            if task.status == "triage" and by_policy:
                raise MutationError(
                    f"Task {task.id} is a request no user has accepted; Foreman may not start it."
                )
            if task.status not in ("todo", "triage"):
                raise MutationError(
                    f"Task {task.id} is {task.status}; only backlog work can be planned."
                )
        assert backlog is not None
        requests = {task.id for task in tasks if task.status == "triage"}

        created: Sprint | None = None
        if sprint is not None:
            self._require_plannable(sprint, project_id)
            target = sprint
        else:
            existing = self.store.list_sprints(project_id)
            created = Sprint(
                id=slug_id("sprint", title, self.store.get_sprint),
                project_id=project_id,
                title=title,
                goal=(new_sprint_goal or "").strip() or None,
                status="planned",
                order_index=max((s.order_index for s in existing), default=-1) + 1,
                created_at=self._now().isoformat(),
            )
            target = created
        try:
            self.store.move_tasks_to_sprint(
                [task.id for task in tasks],
                from_sprint_id=backlog.id,
                from_statuses=("todo", "triage"),
                to_sprint_id=target.id,
                new_sprint=created,
            )
        except StaleTaskError as exc:
            raise MutationError(str(exc)) from exc

        planned: list[Task] = []
        for task in tasks:
            fresh = self.store.get_task(task.id)
            assert fresh is not None
            if fresh.id in requests:
                fresh.status = "todo"
                self.store.save_task(fresh)
            self._audit(
                fresh,
                "engine.task_pulled" if pulled else "human.task_planned",
                step="plan",
                sprint_id=target.id,
                sprint_title=target.title,
                new_sprint=True if created is not None else None,
                accepted=True if fresh.id in requests else None,
            )
            planned.append(fresh)
        return PlannedTasks(sprint=target, tasks=tuple(planned), created_sprint=created is not None)

    def unplan_task(self, task: Task) -> Task:
        """Move a task that has not started from its sprint back to the backlog.

        It keeps its state: a filed task stays filed, an accepted one stays
        accepted.
        """

        if self._in_backlog(task):
            raise MutationError(f"Task {task.id} is already in the backlog.")
        if task.status not in _NOT_STARTED_STATUSES:
            raise MutationError(
                f"Task {task.id} is {task.status}; only a task that has not started "
                "(todo or triage) can go back to the backlog."
            )
        self._refuse_if_running(task, "unplan")
        from_sprint = self.store.get_sprint(task.sprint_id)
        backlog = self.store.ensure_backlog(task.project_id, created_at=self._now().isoformat())
        try:
            self.store.move_tasks_to_sprint(
                [task.id],
                from_sprint_id=task.sprint_id,
                from_statuses=_NOT_STARTED_STATUSES,
                to_sprint_id=backlog.id,
            )
        except StaleTaskError as exc:
            raise MutationError(str(exc)) from exc
        moved = self.store.get_task(task.id)
        assert moved is not None
        self._audit(
            moved,
            "human.task_unplanned",
            step="unplan",
            from_sprint_id=task.sprint_id,
            from_sprint_title=from_sprint.title if from_sprint is not None else None,
            status=moved.status,
        )
        return moved

    def _in_backlog(self, task: Task) -> bool:
        sprint = self.store.get_sprint(task.sprint_id)
        return sprint is not None and sprint.is_backlog

    def _require_plannable(self, sprint: Sprint, project_id: str) -> None:
        """Refuse a destination sprint work cannot be planned into."""

        if sprint.project_id != project_id:
            raise MutationError(f"Sprint {sprint.id} belongs to another project.")
        if sprint.is_backlog:
            raise MutationError("The backlog is not a sprint; file work into it instead.")
        if sprint.status not in PLANNABLE_SPRINT_STATUSES:
            raise MutationError(
                f"Sprint '{sprint.title}' is {sprint.status}; work can only be planned "
                "into a planned or active sprint."
            )
