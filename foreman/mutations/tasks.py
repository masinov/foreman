"""A person's changes to one task: accept, block and unblock, cancel, mark
done and reopen, delete, edit, and guidance for its next step.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..definitions.gate_steps import blocked_kind, resolve_gate_steps
from ..domain.models import (
    TASK_COMPLEXITIES,
    TASK_TYPES,
    Event,
    Sprint,
    Task,
    validate_executor_overrides,
)
from .backlog import PLANNABLE_SPRINT_STATUSES
from .base import _RESOLVED_TASK_STATUSES, MutationBase, MutationError, slug_id

#: Task fields a person may edit, and the statuses whose edits an agent must
#: hear about (they are recorded as ``human.task_edited``).
TASK_EDIT_FIELDS: tuple[str, ...] = (
    "title",
    "task_type",
    "acceptance_criteria",
    "description",
    "priority",
    "complexity",
    "depends_on_task_ids",
    "executor_overrides",
)


#: Statuses in which what a task waits for can still change: once it has
#: started, the engine no longer looks at its dependencies.
_DEPENDENCY_EDIT_STATUSES = frozenset({"triage", "todo"})


_EDIT_AUDITED_STATUSES = frozenset({"in_progress", "blocked"})


@dataclass(frozen=True)
class TaskRemoval:
    """What cancelling or deleting a task did to its worktree."""

    task: Task
    removed_worktree: str | None = None
    warning: str | None = None
    changed: bool = True


class TaskMutations(MutationBase):
    """Changes to one task, checked and audited."""

    def accept_task(self, task: Task) -> Task:
        """Accept filed work: ``triage`` becomes ``todo``.

        A backlog task stays in the backlog, accepted and not planned; a task
        filed straight into a sprint joins that sprint's queue.
        """

        if task.status != "triage":
            raise MutationError(
                f"Cannot accept a task with status '{task.status}'; only tasks in "
                "triage can be accepted."
            )
        task.status = "todo"
        self.store.save_task(task)
        self._audit(task, "human.task_accepted", step="triage", from_status="triage")
        return task

    def block_task(self, task: Task, reason: str) -> Task:
        """Hold a task, with a reason, until someone unblocks it (ADR-0043).

        A task whose step is running is blocked when the step ends: the
        engine owns the task's status until then, so the Block waits on the
        task (``block_requested``) and holds it meanwhile. Unblock starts
        the task's workflow over, as it always has.
        """

        if self._in_backlog(task):
            raise MutationError(
                f"Task {task.id} is in the backlog, where nothing runs; there is nothing "
                "to block. Decline it, or plan it into a sprint first."
            )
        if task.status not in ("todo", "in_progress"):
            raise MutationError(
                f"Task {task.id} cannot be blocked from status {task.status}; only a task "
                "that is queued or under way can be."
            )
        if task.block_requested:
            raise MutationError(f"Task {task.id} is already being blocked.")
        running = self.store.list_runs(task_id=task.id, status="running")
        if any(run.role_id in ("_builtin:merge", "_builtin:mark_done") for run in running):
            # Blocked after its merge, it would start over from the first
            # step on a branch that is already merged.
            raise MutationError(
                f"Task {task.id} is being merged; block it once the merge has ended, "
                "or reopen it later."
            )
        engine_on_it = bool(running) or self.store.get_active_lease(
            project_id=task.project_id, resource_type="task", resource_id=task.id
        ) is not None
        if task.status == "in_progress" and engine_on_it:
            # The engine owns the task's status while it works on it, and its
            # next write would undo a block made now: the Block waits on the
            # task, holds it, and is applied when the engine lets it go.
            self.store.request_task_block(task.id, reason=reason)
            fresh = self.store.get_task(task.id) or task
            self._audit(
                fresh,
                "human.task_blocked",
                step="block",
                from_status=task.status,
                reason=reason,
                after_step=task.workflow_current_step,
            )
            return fresh
        from_status = task.status
        task.status = "blocked"
        task.blocked_reason = reason
        task.completed_at = None
        # Unblock starts the workflow over; a resume step left here could
        # read as a gate waiting for a decision.
        task.workflow_current_step = None
        task.workflow_carried_output = None
        self.store.save_task(task)
        self.store.clear_task_hold(task.id)
        self._audit(task, "human.task_blocked", step="block", from_status=from_status, reason=reason)
        return self.store.get_task(task.id) or task

    def unblock_task(self, task: Task) -> Task:
        """Return a blocked task to the queue, starting its workflow over.

        A Block still waiting for the task's step to end is withdrawn
        instead, and the task carries on where it is.
        """

        if task.block_requested and self.store.withdraw_task_block_request(task.id):
            if task.status != "blocked":
                fresh = self.store.get_task(task.id) or task
                self._audit(
                    fresh,
                    "human.task_unblocked",
                    step="unblock",
                    from_status=task.status,
                    reason=task.block_requested,
                )
                return fresh
            # Blocked meanwhile by the engine itself: the request is moot,
            # and Unblock goes on to unblock the task.
            task.block_requested = None
        if task.status != "blocked":
            raise MutationError(f"Task {task.id} is not blocked.")
        project = self.store.get_project(task.project_id)
        gates = resolve_gate_steps(self.store, project)
        if blocked_kind(task, gates) == "gate":
            raise MutationError(
                f"Task {task.id} is paused at a workflow gate; use `foreman approve` "
                "or `foreman deny` instead."
            )
        reason = task.blocked_reason
        task.status = "todo"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.step_visit_counts = {}
        task.completed_at = None
        self.store.save_task(task)
        self._audit(
            task, "human.task_unblocked", step="unblock", from_status="blocked", reason=reason
        )
        return task

    def cancel_task(self, task: Task) -> TaskRemoval:
        """Cancel a task and remove its worktree. Cancelling twice changes nothing."""

        if task.status == "done":
            raise MutationError(f"Task {task.id} is already done and cannot be cancelled.")
        if task.status == "cancelled":
            return TaskRemoval(task=task, changed=False)
        self._refuse_if_running(task, "cancel")
        from_status = task.status
        task.status = "cancelled"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.completed_at = self._now().isoformat()
        removed, warning = self._discard_worktree(task)
        self.store.save_task(task)
        self.store.clear_task_hold(task.id)
        self._audit(task, "human.task_cancelled", step="cancel", from_status=from_status)
        return TaskRemoval(task=task, removed_worktree=removed, warning=warning)

    def complete_task(self, task: Task, reason: str) -> Task:
        """Mark a task done on a person's word, without running its workflow.

        For work that was finished outside the engine (merged by hand, done
        elsewhere, or no longer needed as a step-by-step run). The reason is
        recorded: the event is the only trace that Foreman did not verify
        this. The worktree is left alone, because it may hold work nobody
        has committed; `foreman worktree prune` removes it later.
        """

        if task.status not in ("todo", "in_progress", "blocked"):
            raise MutationError(
                f"Task {task.id} is {task.status}; only a queued, unfinished or "
                "blocked task can be marked done."
            )
        if self._in_backlog(task):
            raise MutationError(
                f"Task {task.id} is in the backlog. Plan it into a sprint first, "
                "or decline it."
            )
        self._refuse_if_running(task, "mark done")
        from_status = task.status
        from_step = task.workflow_current_step
        task.status = "done"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.completed_at = self._now().isoformat()
        self.store.save_task(task)
        self.store.clear_task_hold(task.id)
        self._audit(
            task,
            "human.task_completed",
            step="complete",
            from_status=from_status,
            from_step=from_step,
            reason=reason,
        )
        return task

    def reopen_task(self, task: Task) -> Task:
        """Return a done or cancelled task to the queue, workflow from the start.

        What was merged stays merged and the branch is kept; a cancelled
        task's worktree was removed and is made again when the task runs.
        """

        if task.status not in _RESOLVED_TASK_STATUSES:
            raise MutationError(
                f"Task {task.id} is {task.status}; only a done or cancelled task "
                "can be reopened."
            )
        sprint = self.store.get_sprint(task.sprint_id)
        if sprint is not None and not sprint.is_backlog and sprint.status not in PLANNABLE_SPRINT_STATUSES:
            raise MutationError(
                f"Sprint '{sprint.title}' is {sprint.status}, so nothing in it runs "
                "again. File a new task for the remaining work."
            )
        from_status = task.status
        task.status = "todo"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.step_visit_counts = {}
        task.completed_at = None
        self.store.save_task(task)
        self.store.clear_task_hold(task.id)
        self._audit(task, "human.task_reopened", step="reopen", from_status=from_status)
        return self.join_sprint_pause(self.store.get_task(task.id) or task)

    def delete_task(self, task: Task) -> TaskRemoval:
        """Delete a task with its history and its worktree.

        There is no audit event: the events of a deleted task are deleted
        with it.
        """

        self._refuse_if_running(task, "delete")
        removed, warning = self._discard_worktree(task)
        self.store.delete_task(task.id)
        return TaskRemoval(task=task, removed_worktree=removed, warning=warning)

    def edit_task(
        self,
        task: Task,
        changes: Mapping[str, Any],
        *,
        valid_steps: set[str] | None = None,
    ) -> dict[str, Any]:
        """Change a task's fields; return the fields that changed, new values.

        ``changes`` names fields of ``TASK_EDIT_FIELDS``. An edit to a task an
        agent is working on (in progress or blocked) is recorded as
        ``human.task_edited`` so the next step can account for it; so is any
        edit made through a proposal. ``valid_steps`` are the workflow's step
        ids, for checking per-step overrides.
        """

        unknown = sorted(set(changes) - set(TASK_EDIT_FIELDS))
        if unknown:
            raise MutationError(f"Unknown task fields: {unknown}")
        changed: dict[str, Any] = {}
        if "title" in changes:
            value = str(changes["title"] or "").strip()
            if not value:
                raise MutationError("Task title cannot be empty.")
            if value != task.title:
                changed["title"] = value
            task.title = value
        if "task_type" in changes:
            value = str(changes["task_type"])
            if value not in TASK_TYPES:
                raise MutationError(
                    f"Unsupported task type: {value}. Expected one of: {', '.join(TASK_TYPES)}."
                )
            if value != task.task_type:
                changed["task_type"] = value
            task.task_type = value  # type: ignore[assignment]
        if "acceptance_criteria" in changes:
            value = changes["acceptance_criteria"]
            normalised = str(value).strip() if value else None
            if normalised != task.acceptance_criteria:
                changed["acceptance_criteria"] = normalised
            task.acceptance_criteria = normalised
        if "description" in changes:
            value = changes["description"]
            normalised = str(value).strip() if value is not None else None
            if normalised != task.description:
                changed["description"] = normalised
            task.description = normalised
        if "priority" in changes:
            try:
                priority = int(changes["priority"])
            except (TypeError, ValueError) as exc:
                raise MutationError("Priority must be an integer.") from exc
            if priority != task.priority:
                changed["priority"] = priority
            task.priority = priority
        if "complexity" in changes:
            value = changes["complexity"]
            complexity = str(value).strip() if value else None
            if complexity is not None and complexity not in TASK_COMPLEXITIES:
                raise MutationError(
                    f"Unsupported complexity: {complexity}. "
                    f"Expected one of: {', '.join(TASK_COMPLEXITIES)}."
                )
            if complexity != task.complexity:
                changed["complexity"] = complexity
            task.complexity = complexity
        if "depends_on_task_ids" in changes:
            wanted = self._checked_dependencies(task, changes["depends_on_task_ids"])
            if wanted != list(task.depends_on_task_ids or []):
                if task.status not in _DEPENDENCY_EDIT_STATUSES:
                    raise MutationError(
                        f"Task {task.id!r} is {task.status}: what it waits for can only "
                        "change before it starts."
                    )
                changed["depends_on_task_ids"] = wanted
                task.depends_on_task_ids = wanted
        if "executor_overrides" in changes:
            try:
                overrides = validate_executor_overrides(
                    changes["executor_overrides"], valid_steps=valid_steps
                )
            except ValueError as exc:
                raise MutationError(str(exc)) from exc
            if overrides != (task.executor_overrides or {}):
                changed["executor_overrides"] = overrides
            task.executor_overrides = overrides
        self.store.save_task(task)
        if changed and (task.status in _EDIT_AUDITED_STATUSES or self.proposal_id):
            self._audit(task, "human.task_edited", step="edit", changed_fields=changed)
        return changed

    def _checked_dependencies(self, task: Task, value: Any) -> list[str]:
        """The tasks ``task`` is to wait for, checked: real, its project's, no loop."""

        if value is None:
            return []
        if isinstance(value, str) or not isinstance(value, (list, tuple)):
            raise MutationError("Dependencies must be a list of task ids.")
        wanted: list[str] = []
        for entry in value:
            dep_id = str(entry).strip()
            if not dep_id or dep_id in wanted:
                continue
            if dep_id == task.id:
                raise MutationError("A task cannot wait for itself.")
            dependency = self.store.get_task(dep_id)
            if dependency is None or dependency.project_id != task.project_id:
                raise MutationError(f"Dependency task not found in this project: {dep_id}")
            if self._waits_for(dependency, task.id):
                raise MutationError(
                    f"Task {dep_id!r} already waits for {task.id!r}, directly or through "
                    "other tasks; making each wait for the other would stop both."
                )
            wanted.append(dep_id)
        return wanted

    def _waits_for(self, task: Task, target_id: str) -> bool:
        """Whether ``task`` waits for ``target_id``, directly or through others."""

        seen: set[str] = set()
        pending = list(task.depends_on_task_ids or [])
        while pending:
            dep_id = pending.pop()
            if dep_id == target_id:
                return True
            if dep_id in seen:
                continue
            seen.add(dep_id)
            dependency = self.store.get_task(dep_id)
            if dependency is not None:
                pending.extend(dependency.depends_on_task_ids or [])
        return False

    def record_guidance(self, task: Task, text: str) -> Event:
        """Record a guidance note the task's next agent step reads (``human.message``)."""

        clean = (text or "").strip()
        if not clean:
            raise MutationError("Guidance text is required.")
        return self._audit(task, "human.message", step="message", text=clean)

    def add_task(
        self,
        sprint: Sprint,
        *,
        title: str,
        task_type: str = "feature",
        description: str | None = None,
        acceptance_criteria: str | None = None,
        complexity: str | None = None,
        depends_on: Sequence[str] = (),
        order_index: int | None = None,
    ) -> Task:
        """Add a task to the end of a sprint's queue.

        Work for the backlog is filed with ``file_task`` (ADR-0021); a sprint's
        own task is added here, from ``foreman task add``, the dashboard and a
        new sprint's first tasks alike. ``depends_on`` names tasks of the same
        project.
        """

        if sprint.is_backlog:
            raise MutationError(
                f"{sprint.id} is the backlog, not a sprint. File work into it with "
                f"`foreman backlog add {sprint.project_id}`."
            )
        clean = (title or "").strip()
        if not clean:
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
        depends_on_ids: list[str] = []
        for raw in depends_on:
            dep_id = str(raw).strip()
            if not dep_id:
                continue
            dependency = self.store.get_task(dep_id)
            if dependency is None or dependency.project_id != sprint.project_id:
                raise MutationError(
                    f"Dependency task {dep_id} not found in project {sprint.project_id}."
                )
            if dep_id not in depends_on_ids:
                depends_on_ids.append(dep_id)
        if order_index is None:
            existing = self.store.list_tasks(sprint_id=sprint.id)
            order_index = max((item.order_index for item in existing), default=-1) + 1
        task = Task(
            id=slug_id("task", clean, self.store.get_task),
            sprint_id=sprint.id,
            project_id=sprint.project_id,
            title=clean,
            task_type=task_type,  # type: ignore[arg-type]
            acceptance_criteria=(acceptance_criteria or "").strip() or None,
            description=(description or "").strip() or None,
            complexity=complexity,
            depends_on_task_ids=depends_on_ids,
            order_index=order_index,
            created_by=self.role,
            created_at=self._now().isoformat(),
        )
        return self.join_sprint_pause(self.store.save_task(task))
