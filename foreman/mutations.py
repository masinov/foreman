"""Changes a person makes to tasks and sprints, in one place.

The CLI and the dashboard both let a person accept, edit, block, unblock,
cancel and delete tasks, write guidance and decide gates, create, edit and
move sprints through their lifecycle, and file, decline, plan and unplan
backlog work (ADR-0021). Confirming a manager's proposal (ADR-0022) applies
the same operations. They used to
carry their own copies of the rules, which had drifted apart, and only some
dashboard actions left a trace. ``Mutations`` is the single implementation:
it checks the change is allowed, refuses what a running engine is in the
middle of, writes it, and records an audit event saying who did it and from
where.

Surfaces translate ``MutationError`` into their own error type and decide
how to present the result. Nothing here prints or knows about HTTP.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .engine_control import blocked_kind, resolve_gate_steps
from .errors import ForemanError
from .models import (
    TASK_COMPLEXITIES,
    TASK_TYPES,
    Event,
    Project,
    Run,
    Sprint,
    SprintStatus,
    Task,
    validate_executor_overrides,
)
from .notifications import NotificationDispatcher
from .policy import PolicyDecision, PolicyMatrix
from .store import ForemanStore
from .store.sprints import StaleTaskError
from .worktrees import WorktreeError, WorktreeManager

#: Where a sprint may go from each status.
SPRINT_TRANSITIONS: dict[str, tuple[SprintStatus, ...]] = {
    "planned": ("active", "cancelled"),
    "active": ("completed", "cancelled"),
    "completed": (),
    "cancelled": (),
}

_RESOLVED_TASK_STATUSES = frozenset({"done", "cancelled"})

#: Sprints backlog work can be planned into.
PLANNABLE_SPRINT_STATUSES: tuple[SprintStatus, ...] = ("planned", "active")

#: Task statuses that mean "not started": the only ones that may go back to
#: the backlog from a sprint.
_NOT_STARTED_STATUSES: tuple[str, ...] = ("triage", "todo")

#: Task fields a person may edit, and the statuses whose edits an agent must
#: hear about (they are recorded as ``human.task_edited``).
TASK_EDIT_FIELDS: tuple[str, ...] = (
    "title",
    "task_type",
    "acceptance_criteria",
    "description",
    "priority",
    "executor_overrides",
)
_EDIT_AUDITED_STATUSES = frozenset({"in_progress", "blocked"})

#: Sprint fields a person may edit outside its lifecycle.
SPRINT_EDIT_FIELDS: tuple[str, ...] = ("title", "goal", "order_index")

#: Gate decisions, as the workflow names them.
GATE_OUTCOMES: tuple[str, ...] = ("approve", "deny")


def slug_id(prefix: str, title: str, exists: Callable[[str], object | None]) -> str:
    """Return ``<prefix>-<slug of title>``, numbered when already taken."""

    normalized = unicodedata.normalize("NFKD", title.strip().lower())
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:48] or "untitled"
    candidate = f"{prefix}-{slug}"
    suffix = 2
    while exists(candidate) is not None:
        candidate = f"{prefix}-{slug}-{suffix}"
        suffix += 1
    return candidate


class MutationError(ForemanError):
    """A requested change is not allowed. The message says why."""


@dataclass(frozen=True)
class TaskRemoval:
    """What cancelling or deleting a task did to its worktree."""

    task: Task
    removed_worktree: str | None = None
    warning: str | None = None
    changed: bool = True


@dataclass(frozen=True)
class FiledTask:
    """A task filed into the backlog, with the triage decision that set its state."""

    task: Task
    triage: PolicyDecision
    accepted_by_filer: bool = False


@dataclass(frozen=True)
class GateDecision:
    """A gate decision recorded, and the step the task now waits at."""

    task: Task
    outcome: str
    next_step: str | None
    deferred: bool


@dataclass(frozen=True)
class PlannedTasks:
    """Tasks planned into a sprint, and whether the sprint was created for them."""

    sprint: Sprint
    tasks: tuple[Task, ...]
    created_sprint: bool


class Mutations:
    """Operator changes to the tasks and sprints of one store.

    ``via`` names the surface (``"cli"``, ``"dashboard"``, ``"api"``,
    ``"engine"``) and ``actor`` who acted, when known; both are recorded on
    every audit event. ``role`` is the role recorded on the event and on the
    run it hangs from: ``"human"`` for a person, ``"api"`` for another
    system, an agent's role for work an agent files.

    ``proposal_id`` is set while a confirmed proposal is applied (ADR-0022):
    every audit event names it, and edits and gate decisions, which are
    otherwise recorded elsewhere or not at all, get an event of their own.

    ``defer_side_effects`` keeps work outside the database (removing a
    cancelled task's worktree) out of the write: it is queued on
    ``deferred`` for the caller to run once the transaction has committed,
    or to drop.
    """

    def __init__(
        self,
        store: ForemanStore,
        *,
        via: str,
        actor: str | None = None,
        role: str = "human",
        now: Callable[[], datetime] | None = None,
        proposal_id: str | None = None,
        defer_side_effects: bool = False,
    ) -> None:
        self.store = store
        self.via = via
        self.actor = actor
        self.role = role
        self.proposal_id = proposal_id
        self.defer_side_effects = defer_side_effects
        self.deferred: list[Callable[[], str | None]] = []
        self._now = now or (lambda: datetime.now(timezone.utc))

    # ── tasks ────────────────────────────────────────────────────────────

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
        """Park a task. An engine running it stops when its current step ends."""

        if task.status in _RESOLVED_TASK_STATUSES or task.status == "declined":
            raise MutationError(f"Task {task.id} cannot be blocked from status {task.status}.")
        if self._in_backlog(task):
            raise MutationError(
                f"Task {task.id} is in the backlog, where nothing runs; there is nothing "
                "to block. Decline it, or plan it into a sprint first."
            )
        from_status = task.status
        task.status = "blocked"
        task.blocked_reason = reason
        task.completed_at = None
        self.store.save_task(task)
        self._audit(task, "human.task_blocked", step="block", from_status=from_status, reason=reason)
        return task

    def unblock_task(self, task: Task) -> Task:
        """Return a blocked task to the queue, starting its workflow over."""

        if task.status != "blocked":
            raise MutationError(f"Task {task.id} is not blocked.")
        project = self.store.get_project(task.project_id)
        gates = resolve_gate_steps(project.workflow_id if project is not None else None)
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
        self._audit(task, "human.task_reopened", step="reopen", from_status=from_status)
        return task

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

    def record_guidance(self, task: Task, text: str) -> Event:
        """Record a guidance note the task's next agent step reads (``human.message``)."""

        clean = (text or "").strip()
        if not clean:
            raise MutationError("Guidance text is required.")
        return self._audit(task, "human.message", step="message", text=clean)

    def decide_gate(self, task: Task, outcome: str, note: str | None = None) -> GateDecision:
        """Approve or deny a task waiting at a human gate of its workflow.

        The decision is recorded and the task left at the step it leads to,
        for the project's engine to run (ADR-0011); nothing runs here.
        """

        from .orchestrator import ForemanOrchestrator, OrchestratorError

        if outcome not in GATE_OUTCOMES:
            raise MutationError(f"Unknown gate decision: {outcome}.")
        clean_note = (note or "").strip() or None
        try:
            result = ForemanOrchestrator(self.store).resume_human_gate(
                task.id, outcome=outcome, note=clean_note, defer=True
            )
        except OrchestratorError as exc:
            raise MutationError(str(exc)) from exc
        decided = self.store.get_task(task.id) or task
        if self.proposal_id:
            # The gate's own records (workflow.resumed, the decision row) have
            # no place for the proposal; this event names it.
            self._audit(
                decided,
                "human.gate_decided",
                step="gate",
                decision=outcome,
                note=clean_note,
                next_step=result.next_step,
            )
        return GateDecision(
            task=decided, outcome=outcome, next_step=result.next_step, deferred=result.deferred
        )

    def send_back(self, task: Task, guidance: str) -> Task:
        """Send a task that waits for a person back to work, with guidance.

        At a human gate it is the workflow's denial, carrying the guidance to
        the step a refusal leads to. A blocked task goes back to the queue
        (``unblock_task``) and the guidance is recorded for its next step.
        """

        clean = (guidance or "").strip()
        if not clean:
            raise MutationError("Say what should change: guidance is required to send a task back.")
        if task.status != "blocked":
            raise MutationError(
                f"Task {task.id} is {task.status}, not waiting for a person; only a task "
                "waiting at a gate or blocked can be sent back."
            )
        project = self.store.get_project(task.project_id)
        gates = resolve_gate_steps(project.workflow_id if project is not None else None)
        if blocked_kind(task, gates) == "gate":
            return self.decide_gate(task, "deny", clean).task
        unblocked = self.unblock_task(task)
        self.record_guidance(unblocked, clean)
        return unblocked

    # ── the backlog (ADR-0021) ───────────────────────────────────────────

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
        filed = triage.value == "human" and not accept
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
            accepted_by_filer=True if accept and triage.value == "human" else None,
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
    ) -> PlannedTasks:
        """Plan accepted backlog tasks into a sprint, all or none.

        The sprint is either ``sprint`` (planned or active) or a new planned
        sprint titled ``new_sprint_title``, created in the same transaction.
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
        for task in tasks:
            if backlog is None or task.sprint_id != backlog.id:
                raise MutationError(
                    f"Task {task.id} is not in the backlog (it is in sprint {task.sprint_id})."
                )
            if task.status == "triage":
                raise MutationError(
                    f"Task {task.id} is filed but not accepted; accept it before planning it."
                )
            if task.status != "todo":
                raise MutationError(
                    f"Task {task.id} is {task.status}; only accepted tasks can be planned."
                )
        assert backlog is not None

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
                from_statuses=("todo",),
                to_sprint_id=target.id,
                new_sprint=created,
            )
        except StaleTaskError as exc:
            raise MutationError(str(exc)) from exc

        planned: list[Task] = []
        for task in tasks:
            fresh = self.store.get_task(task.id)
            assert fresh is not None
            self._audit(
                fresh,
                "human.task_planned",
                step="plan",
                sprint_id=target.id,
                sprint_title=target.title,
                new_sprint=True if created is not None else None,
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

    # ── sprints ──────────────────────────────────────────────────────────

    def transition_sprint(self, sprint: Sprint, target_status: str) -> Sprint:
        """Move a sprint to ``target_status``. Moving it where it already is changes nothing."""

        if sprint.is_backlog:
            raise MutationError(
                "The backlog is not a sprint: it cannot be activated, completed or cancelled."
            )
        if sprint.status == target_status:
            return sprint
        allowed = SPRINT_TRANSITIONS.get(sprint.status, ())
        if target_status not in allowed:
            raise MutationError(
                f"Cannot transition sprint from '{sprint.status}' to '{target_status}'. "
                f"Allowed: {list(allowed) or 'none'}."
            )
        if target_status == "active":
            active = self.store.get_active_sprint(sprint.project_id)
            if active is not None and active.id != sprint.id:
                raise MutationError(
                    f"Sprint '{active.title}' is already active. "
                    "Complete or cancel it before activating another sprint."
                )
        if target_status == "completed":
            unresolved = [
                task.task_key or task.id
                for task in self.store.list_tasks(sprint_id=sprint.id)
                if task.status not in _RESOLVED_TASK_STATUSES
            ]
            if unresolved:
                raise MutationError(
                    "Sprint cannot be completed while unresolved tasks remain: "
                    + ", ".join(unresolved)
                    + ". Finish or cancel them, or cancel the sprint."
                )
        now = self._now().isoformat()
        sprint.status = target_status  # type: ignore[assignment]
        if target_status == "active":
            sprint.started_at = sprint.started_at or now
            sprint.completed_at = None
        if target_status in ("completed", "cancelled"):
            sprint.started_at = sprint.started_at or (now if target_status == "completed" else None)
            sprint.completed_at = now
        self.store.save_sprint(sprint)
        return sprint

    def create_sprint(self, project: Project, *, title: str, goal: str | None = None) -> Sprint:
        """Create a planned sprint at the end of the project's queue."""

        clean = (title or "").strip()
        if not clean:
            raise MutationError("Sprint title is required.")
        existing = self.store.list_sprints(project.id)
        sprint = Sprint(
            id=slug_id("sprint", clean, self.store.get_sprint),
            project_id=project.id,
            title=clean,
            goal=(goal or "").strip() or None,
            status="planned",
            order_index=max((s.order_index for s in existing), default=-1) + 1,
            created_at=self._now().isoformat(),
        )
        self.store.save_sprint(sprint)
        return sprint

    def edit_sprint(self, sprint: Sprint, changes: Mapping[str, Any]) -> Sprint:
        """Change a sprint's title, goal or place in the queue (``SPRINT_EDIT_FIELDS``)."""

        if sprint.is_backlog:
            raise MutationError("The backlog is not a sprint and cannot be edited.")
        unknown = sorted(set(changes) - set(SPRINT_EDIT_FIELDS))
        if unknown:
            raise MutationError(f"Unknown sprint fields: {unknown}")
        if not changes:
            raise MutationError("No fields provided for update.")
        if "title" in changes:
            value = str(changes["title"] or "").strip()
            if not value:
                raise MutationError("Sprint title cannot be empty.")
            sprint.title = value
        if "goal" in changes:
            value = changes["goal"]
            sprint.goal = str(value).strip() or None if value else None
        if "order_index" in changes:
            try:
                sprint.order_index = int(changes["order_index"])
            except (TypeError, ValueError) as exc:
                raise MutationError("order_index must be an integer.") from exc
        self.store.save_sprint(sprint)
        return sprint

    def move_sprint(self, sprint: Sprint, direction: str) -> Sprint:
        """Move a planned sprint one place earlier (``up``) or later (``down``) in the queue.

        Only planned sprints have an order a person can change: the active one
        is running and finished ones are history. Moving the first one up or
        the last one down changes nothing. The planned sprints are renumbered
        in one transaction, so the queue never shows a half-applied order.
        """

        if direction not in ("up", "down"):
            raise MutationError("direction must be 'up' or 'down'.")
        if sprint.is_backlog:
            raise MutationError("The backlog is not a sprint and has no place in the queue.")
        if sprint.status != "planned":
            raise MutationError(
                f"Sprint '{sprint.title}' is {sprint.status}; only a planned sprint can be moved in the queue."
            )
        everything = self.store.list_sprints(sprint.project_id)
        planned = [entry for entry in everything if entry.status == "planned"]
        position = next(index for index, entry in enumerate(planned) if entry.id == sprint.id)
        target = position - 1 if direction == "up" else position + 1
        if target < 0 or target >= len(planned):
            return sprint
        planned[position], planned[target] = planned[target], planned[position]
        # Planned sprints run after everything that is not planned, so they
        # are numbered after it; this also repairs equal numbers, which
        # swapping two values would leave in place.
        first = max((entry.order_index for entry in everything if entry.status != "planned"), default=-1) + 1
        with self.store.atomic():
            for offset, entry in enumerate(planned):
                if entry.order_index != first + offset:
                    entry.order_index = first + offset
                    self.store.save_sprint(entry)
        return next(entry for entry in planned if entry.id == sprint.id)

    def delete_sprint(self, sprint: Sprint) -> None:
        """Delete a sprint with its tasks, runs and events."""

        if sprint.is_backlog:
            raise MutationError("The backlog is not a sprint and cannot be deleted.")
        for task in self.store.list_tasks(sprint_id=sprint.id):
            self._refuse_if_running(task, "delete")
        self.store.delete_sprint(sprint.id)

    # ── shared ───────────────────────────────────────────────────────────

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

    def _attention(self, task: Task, project: Project, *, trigger: str, run_id: str) -> Event:
        """Raise one attention turn for a task that waits for a person."""

        now = self._now()
        notify = (
            PolicyMatrix.for_project(project)
            .resolve("notification", task_type=task.task_type, overrides=task.executor_overrides)
            .value
        )
        event = self.store.save_event(
            Event(
                id=f"evt-attention-{now.strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex[:8]}",
                run_id=run_id,
                task_id=task.id,
                project_id=project.id,
                event_type="engine.attention_needed",
                role_id=self.role,
                timestamp=now.isoformat(),
                payload={"trigger": trigger, "task_id": task.id, "notify": notify},
            )
        )
        # Queue only; the delivery worker sends. The dispatcher never raises.
        NotificationDispatcher(self.store).consider(event)
        return event

    def _refuse_if_running(self, task: Task, verb: str) -> None:
        """Refuse a change to a task an engine is executing right now.

        The engine would overwrite the row with its next save, or keep
        working on a task that no longer exists. It has to stop first.
        """

        running = self.store.list_runs(task_id=task.id, status="running")
        if running and self.store.get_engine_lock(task.project_id) is not None:
            raise MutationError(
                f"Task {task.id} has a running agent step ({running[0].id}). Stop it "
                f"first with `foreman engine stop-task {task.project_id} {task.id}` "
                f"(or Stop in the dashboard), then {verb} it."
            )

    def _discard_worktree(self, task: Task) -> tuple[str | None, str | None]:
        """Remove a finished task's worktree. Returns (removed path, warning).

        Failing to remove it must not fail the change: the row is what
        matters, and `foreman worktree prune` can clean up later.
        """

        recorded = task.worktree_path
        if not recorded:
            return None, None
        project = self.store.get_project(task.project_id)
        if project is None:
            return None, None
        if self.defer_side_effects:
            self.deferred.append(lambda: self._remove_worktree(project, recorded))
            task.worktree_path = None
            return recorded, None
        warning = self._remove_worktree(project, recorded)
        if warning is not None:
            return None, warning
        task.worktree_path = None
        return recorded, None

    @staticmethod
    def _remove_worktree(project: Project, recorded: str) -> str | None:
        """Remove one worktree; return a warning when that failed."""

        try:
            WorktreeManager(project).remove_path(Path(recorded))
        except (WorktreeError, OSError) as exc:
            return (
                f"Warning: could not remove worktree {recorded}: {exc}. "
                f"Run `foreman worktree prune {project.id}` to clean it up."
            )
        return None

    def _audit(self, task: Task, event_type: str, *, step: str, **payload: object) -> Event:
        """Record who changed a task, on a run that names the surface."""

        now = self._now()
        # Several tasks change in one operation (planning), so the stamp alone
        # does not make the ids unique, and neither does a prefix of task ids
        # that share their first words.
        stamp = f"{now.strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex[:8]}"
        runs = self.store.list_runs(task_id=task.id)
        if runs:
            run_id = runs[-1].id
        else:
            timestamp_text = now.isoformat()
            run = Run(
                id=f"run-{step}-{stamp}-{task.id[:8]}",
                task_id=task.id,
                project_id=task.project_id,
                role_id=self.role,
                workflow_step=step,
                agent_backend=self.via,
                status="completed",
                outcome=step,
                started_at=timestamp_text,
                completed_at=timestamp_text,
                created_at=timestamp_text,
            )
            self.store.save_run(run)
            run_id = run.id
        event = Event(
            id=f"evt-{step}-{stamp}-{task.id[:8]}",
            run_id=run_id,
            task_id=task.id,
            project_id=task.project_id,
            event_type=event_type,
            role_id=self.role,
            timestamp=now.isoformat(),
            payload={
                "task_key": task.task_key,
                "via": self.via,
                "by": self.actor,
                **({"proposal_id": self.proposal_id} if self.proposal_id else {}),
                **{key: value for key, value in payload.items() if value is not None},
            },
        )
        self.store.save_event(event)
        return event
