"""Tasks: one task as its page shows it, creating and editing one, and a
person's actions on it, each through ``foreman.mutations``.
"""

from __future__ import annotations

import re
from typing import Any

from ..definitions.gate_steps import (
    WorkflowGateSteps,
    blocked_kind,
)
from ..definitions.layers import project_definitions
from ..definitions.roles import RoleLoadError
from ..definitions.workflows import WorkflowLoadError
from ..domain.guidance import guidance_notes
from ..domain.models import (
    Event,
    Project,
    Task,
)
from ..domain.policy import PolicyMatrix, describe_resolution
from ..engine.document_changes import changes_by_document
from ..mutations import MutationError
from ..mutations.gates import GateVersionChanged, current_gate_version
from .base import Service
from .errors import (
    ActionFailedError,
    InvalidRequestError,
    NotFoundError,
    VersionChangedError,
)
from .task_models import test_counts
from .views import HoldReader, needed_by, task_filed_from, task_source
from .workspace import foreman_starts_backlog_work


def _serialize_completion_evidence(evidence: "Any") -> dict[str, Any] | None:
    """Serialize a ``CompletionEvidence`` for the task detail payload.

    Returns ``None`` when the task has no evidence yet (the common case before a
    decision role runs).
    """
    if evidence is None:
        return None
    return {
        "proof_status": evidence.proof_status,
        "head_sha": evidence.head_sha,
        "tests_status": evidence.tests_status,
        "tested_sha": evidence.tested_sha,
        "test_exit_code": evidence.test_exit_code,
        "test_duration_seconds": evidence.test_duration_seconds,
        "review_outcome": evidence.review_outcome,
        "reviewed_sha": evidence.reviewed_sha,
        "security_review_outcome": evidence.security_review_outcome,
        "security_reviewed_sha": evidence.security_reviewed_sha,
        "outstanding": list(evidence.outstanding),
        "criteria_count": evidence.criteria_count,
        "criteria_addressed": evidence.criteria_addressed,
        "criteria_partially_addressed": evidence.criteria_partially_addressed,
        "criteria_checklist": list(evidence.criteria()),
        "changed_files": list(evidence.changed_files),
        "branch_diff_stat": evidence.branch_diff_stat,
        "builtin_test_passed": evidence.builtin_test_passed,
        "builtin_test_detail": evidence.builtin_test_detail,
        "failure_reasons": list(evidence.failure_reasons),
        "built_at": evidence.built_at,
    }


def _humanize(identifier: str | None) -> str:
    """A step id as Activity names it: "code_review" is "Code review"."""

    words = re.sub(r"[_-]+", " ", str(identifier or "")).strip()
    return words[:1].upper() + words[1:]


def decision_sentence(
    task: Task,
    *,
    sent_back: bool,
    next_step: str | None,
    engine_resident: bool,
    held: bool = False,
) -> str:
    """The one sentence an approval or a send-back is answered with.

    The dashboard builds the same sentence (``decisionSentence`` in the
    frontend); the CLI and other systems read this one. A task a user holds
    goes on when resumed (ADR-0043); one with no worker, when a worker runs.
    """

    name = task.task_key or task.title
    step = _humanize(next_step)
    if sent_back:
        return f"Sent {name} back to {step}." if step else f"Sent {name} back."
    if not step:
        return f"Approved {name}."
    if held:
        return f"Approved {name}. It goes on with {step} on Resume."
    if engine_resident:
        return f"Approved {name}. Foreman goes on with {step}."
    return f"Approved {name}. It waits at {step} until a worker runs."


class TaskService(Service):
    """Tasks: one task as its page shows it, creating, editing, and a person's actions on it."""

    def _rests_on(self, task: Task) -> list[dict[str, Any]]:
        """The documents the task rests on; one that a merge changed since it was named says which."""

        changes = changes_by_document(self.store, task) if task.rests_on else {}
        items = []
        for ref in task.rests_on:
            item: dict[str, Any] = ref.as_dict()
            change = changes.get(ref.key)
            item["changed"] = (
                {
                    "commit": change.get("merge_sha"),
                    "task_key": change.get("merged_task_key") or None,
                    "at": change.get("timestamp"),
                }
                if change
                else None
            )
            items.append(item)
        return items

    def _dependencies(self, task: Task) -> list[dict[str, Any]]:
        """The tasks ``task`` waits for, named, in the order they were given.

        A dependency that no longer exists is still listed, by id, so the
        page can say that something it waited for is gone.
        """

        named: list[dict[str, Any]] = []
        for dep_id in task.depends_on_task_ids or []:
            dep = self.store.get_task(dep_id)
            named.append(
                {
                    "id": dep_id,
                    "task_key": dep.task_key if dep else None,
                    "title": dep.title if dep else None,
                    "status": dep.status if dep else None,
                }
            )
        return named

    def _closed_by_hand(self, task: Task, events: list[Event]) -> dict[str, Any] | None:
        """Who marked a done task done and why, when a person did.

        A task the engine finished, or one reopened and finished by the
        engine since, has none: only the latest close counts.
        """

        if task.status != "done":
            return None
        latest = None
        for event in events:
            if event.event_type in ("human.task_completed", "human.task_reopened"):
                latest = event
        if latest is None or latest.event_type != "human.task_completed":
            return None
        return {
            "reason": latest.payload.get("reason"),
            "by": latest.payload.get("by"),
            "at": latest.timestamp,
        }

    def _starts_backlog_work(self, project_id: str) -> bool:
        project = self.store.get_project(project_id)
        return bool(project and foreman_starts_backlog_work(project))

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Return one task detail payload including run history."""

        task = self.store.get_task(task_id)
        if task is None:
            raise NotFoundError(f"Task not found: {task_id}")

        project = self.store.get_project(task.project_id)
        gates = self._gate_steps(project)
        events = self.store.list_events(task_id=task.id)

        # How many tests each test step ran, from its last test record (ADR-0035).
        reports = {
            event.run_id: event.payload.get("report")
            for event in sorted(events, key=lambda e: e.timestamp)
            if event.event_type == "engine.test_run"
        }
        runs_data = []
        for run in self.store.list_runs(task_id=task_id):
            counts = test_counts(reports.get(run.id))
            runs_data.append(
                {
                    "id": run.id,
                    "role_id": run.role_id,
                    "workflow_step": run.workflow_step,
                    "agent_backend": run.agent_backend,
                    "status": run.status,
                    "outcome": run.outcome,
                    "outcome_detail": run.outcome_detail,
                    "token_count": run.token_count,
                    "token_usage": run.token_usage.as_dict(),
                    "cost_usd": run.cost_usd,
                    "duration_ms": run.duration_ms,
                    "created_at": run.created_at,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "model": run.model,
                    "session_id": run.session_id,
                    "branch_name": run.branch_name,
                    "commit_sha": run.commit_sha,
                    "record": run.record,
                    "tests": counts.model_dump() if counts is not None else None,
                }
            )

        sprint = self.store.get_sprint(task.sprint_id)
        return {
            "id": task.id,
            "project_id": task.project_id,
            "sprint_id": task.sprint_id,
            "task_key": task.task_key,
            "title": task.title,
            "status": task.status,
            # A "Run next" the engine has not started yet.
            "run_next": task.id in self.store.run_requested_task_ids(task.project_id),
            # In the backlog: a request, backlog work or declined (ADR-0021, ADR-0028).
            "in_backlog": sprint is not None and sprint.is_backlog,
            # Whether accepting a request has an effect in this project.
            "foreman_starts_backlog_work": self._starts_backlog_work(task.project_id),
            "task_type": task.task_type,
            "description": task.description,
            "priority": task.priority,
            "branch_name": task.branch_name,
            "worktree_path": task.worktree_path,
            "assigned_role": task.assigned_role,
            "created_by": task.created_by,
            "created_at": task.created_at,
            "blocked_reason": task.blocked_reason,
            # A user's hold on the task, or on its sprint or the workspace
            # (ADR-0043), and whether a step of it is running (Stop).
            "hold": HoldReader(self.store).hold(task),
            "step_running": bool(self.store.list_runs(task_id=task.id, status="running")),
            "acceptance_criteria": task.acceptance_criteria,
            "rests_on": self._rests_on(task),
            "workflow_current_step": task.workflow_current_step,
            "step_visit_counts": task.step_visit_counts or {},
            "depends_on_task_ids": task.depends_on_task_ids or [],
            "dependencies": self._dependencies(task),
            # What waits for it, so a user sees what holding it holds (ADR-0043).
            "needed_by": needed_by(self.store, task),
            "executor_overrides": task.executor_overrides or {},
            "awaiting_human_gate": self._at_human_gate(task, gates),
            "gate_policy": self._gate_policy(task, gates),
            # What a person at the gate is looking at, to name in the decision.
            "gate_version": self._gate_version(task, project, gates),
            "blocked_kind": blocked_kind(task, gates),
            "completion_evidence": _serialize_completion_evidence(task.completion_evidence),
            "guidance": [
                {
                    "event_id": note.event_id,
                    "text": note.text,
                    "recorded_at": note.recorded_at,
                    "delivered": note.delivered,
                    "delivered_at": note.delivered_at,
                    "delivered_role": note.delivered_role,
                    "delivered_step": note.delivered_step,
                }
                for note in guidance_notes(events)
            ],
            "closed_by_hand": self._closed_by_hand(task, events),
            "source": task_source(task),
            "filed_from": task_filed_from(self.store, events),
            "policy": describe_resolution(
                PolicyMatrix.for_project(project).resolve_task(task)
            )
            if project is not None
            else {},
            "totals": self.store.run_totals(task_id=task_id),
            "runs": runs_data,
        }

    def create_task(
        self,
        sprint_id: str,
        *,
        title: str,
        task_type: str = "feature",
        acceptance_criteria: str | None = None,
        description: str | None = None,
        depends_on: list[str] | None = None,
        rests_on: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Create one task in a sprint.

        Mirrors the ``foreman task add`` CLI surface: optional ``description``,
        and ``depends_on`` task ids (validated to exist in the same project).
        """

        sprint = self._require_sprint(sprint_id)
        try:
            task = self._mutations().add_task(
                sprint,
                title=title,
                task_type=task_type,
                acceptance_criteria=acceptance_criteria,
                description=description,
                depends_on=depends_on or (),
                rests_on=rests_on,
            )
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return {
            "id": task.id,
            "task_key": task.task_key,
            "title": task.title,
            "status": task.status,
            "task_type": task.task_type,
            "acceptance_criteria": task.acceptance_criteria,
            "description": task.description,
            "rests_on": [ref.as_dict() for ref in task.rests_on],
            "depends_on_task_ids": task.depends_on_task_ids,
            "order_index": task.order_index,
            "created_at": task.created_at,
        }

    def update_task_fields(self, task_id: str, *, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply allowed field updates to one task and return its detail payload.

        Emits a ``human.task_edited`` event when the task is in-progress or
        blocked so the change is visible in the activity stream and the agent
        can account for it on its next run.
        """

        task = self._require_task(task_id)
        try:
            self._mutations().edit_task(
                task,
                updates,
                valid_steps=(
                    self._project_workflow_step_ids(task.project_id)
                    if "executor_overrides" in updates
                    else None
                ),
            )
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc

        return self.get_task(task_id)

    def _project_workflow_step_ids(self, project_id: str) -> set[str] | None:
        """Return the workflow step ids for a project, or ``None`` if unresolved."""

        project = self.store.get_project(project_id)
        if project is None:
            return None
        try:
            workflows = project_definitions(self.store, project_id).workflows
        except (RoleLoadError, WorkflowLoadError):
            return None
        workflow = workflows.get(project.workflow_id)
        if workflow is None:
            return None
        return {step.id for step in workflow.steps}

    def accept_task(self, task_id: str) -> dict[str, Any]:
        """Accept one filed task (see ``Mutations.accept_task``)."""

        task = self._require_task(task_id)
        try:
            self._mutations().accept_task(task)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self.get_task(task.id)

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        """Cancel one task that is not already done or cancelled."""

        task = self._require_task(task_id)
        if task.status == "cancelled":
            raise InvalidRequestError(
                f"Cannot cancel a task with status '{task.status}'."
            )
        try:
            removal = self._mutations().cancel_task(task)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return {
            "status": "cancelled",
            "task_id": task_id,
            "removed_worktree": removal.removed_worktree,
        }

    def block_task(
        self, task_id: str, *, reason: str, requested_by: str | None = None
    ) -> dict[str, Any]:
        """Park one task with a reason a person gave (see ``Mutations.block_task``)."""

        task = self._require_task(task_id)
        normalized = (reason or "").strip()
        if not normalized:
            raise InvalidRequestError("Say why the task is blocked.")
        try:
            self._mutations(requested_by).block_task(task, normalized)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self.get_task(task.id)

    def unblock_task(
        self, task_id: str, *, note: str | None = None, requested_by: str | None = None
    ) -> dict[str, Any]:
        """Return a blocked task to the queue (see ``Mutations.unblock_task``).

        ``note`` is guidance for the next agent step: it is recorded the way
        ``create_human_message`` records it, after the task is back in the
        queue, so a refused unblock records nothing.
        """

        task = self._require_task(task_id)
        try:
            self._mutations(requested_by).unblock_task(task)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        if note and note.strip():
            self.create_human_message(task.id, text=note)
        return self.get_task(task.id)

    def complete_task(
        self, task_id: str, *, reason: str, requested_by: str | None = None
    ) -> dict[str, Any]:
        """Mark one task done by hand (see ``Mutations.complete_task``)."""

        task = self._require_task(task_id)
        normalized = (reason or "").strip()
        if not normalized:
            raise InvalidRequestError("Say why the task is done.")
        try:
            self._mutations(requested_by).complete_task(task, normalized)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self.get_task(task.id)

    def reopen_task(self, task_id: str, *, requested_by: str | None = None) -> dict[str, Any]:
        """Return a done or cancelled task to the queue (see ``Mutations.reopen_task``)."""

        task = self._require_task(task_id)
        try:
            self._mutations(requested_by).reopen_task(task)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self.get_task(task.id)

    def delete_task(self, task_id: str) -> dict[str, Any]:
        """Delete one task, its history, and the worktree it was working in."""

        task = self._require_task(task_id)
        project_id = task.project_id
        try:
            self._mutations().delete_task(task)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return {"ok": "deleted", "task_id": task_id, "project_id": project_id}

    def _gate_version(
        self, task: Task, project: Project | None, gates: WorkflowGateSteps
    ) -> dict[str, str | None] | None:
        """The version in front of a person at the gate a task waits at, or ``None``."""

        policy = self._gate_policy(task, gates)
        if project is None or policy is None:
            return None
        version = current_gate_version(self.store, project, task, policy)
        return version.to_dict() if version.kind else None

    def approve_task(self, task_id: str, *, version: str | None = None) -> dict[str, Any]:
        """Resume one human gate with an approval outcome.

        ``version`` is what the person saw (``gate_version`` of the task); an
        approval of a version that has changed is refused with the new one.
        """

        return self._decide_human_gate(task_id, outcome="approve", note=None, version=version)

    def deny_task(self, task_id: str, *, note: str | None = None) -> dict[str, Any]:
        """Resume one human gate with a denial outcome."""

        return self._decide_human_gate(task_id, outcome="deny", note=note)

    def _decide_human_gate(
        self, task_id: str, *, outcome: str, note: str | None, version: str | None = None
    ) -> dict[str, Any]:
        """Record a gate decision and leave the work to the project's engine.

        The web process never runs workflow steps: it holds neither the
        project's engine lock nor a task lease, and an agent step would block
        every other request for as long as it ran. The task is left at the
        step the decision leads to; a resident engine wakes on the change.
        """

        task = self._require_task(task_id)
        try:
            result = self._mutations().decide_gate(
                task, outcome, note, seen_version=version
            )
        except GateVersionChanged as exc:
            raise VersionChangedError(str(exc), exc.current.to_dict()) from exc
        except MutationError as exc:
            raise ActionFailedError(f"Failed to {outcome}: {exc}") from exc
        resident = self.store.get_engine_lock(task.project_id) is not None
        held = HoldReader(self.store).hold(self.store.get_task(task_id) or task) is not None
        return {
            "status": "approved" if outcome == "approve" else "denied",
            "task_id": task_id,
            "next_step": result.next_step,
            "deferred": result.deferred,
            "engine_resident": resident,
            "version": result.version.to_dict(),
            "version_named": result.version_named,
            # A user's hold on it (ADR-0043): the decision waits for Resume.
            "held": held,
            "message": decision_sentence(
                task,
                sent_back=outcome != "approve",
                next_step=result.next_step,
                engine_resident=resident,
                held=held,
            ),
        }

    def create_human_message(self, task_id: str, *, text: str) -> dict[str, Any]:
        """Record one guidance note for a task.

        Recording is all this does. The engine puts the note into the prompt
        of the task's next agent step and marks it delivered then; a finished
        task has no next step, and the response says so instead of "sent".
        """

        task = self._require_task(task_id)
        if not text.strip():
            raise InvalidRequestError("Message text required")
        try:
            event = self._mutations().record_guidance(task, text)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        will_deliver = task.status not in {"done", "cancelled"}
        return {
            "status": "recorded",
            "event_id": event.id,
            "task_id": task_id,
            "will_deliver": will_deliver,
            "message": (
                "Recorded. The next agent step for this task will read it."
                if will_deliver
                else f"Recorded in the task's history. The task is {task.status}, "
                "so no agent step will read it."
            ),
        }
