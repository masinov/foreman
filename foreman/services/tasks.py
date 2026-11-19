"""Tasks: one task as its page shows it, creating and editing one, and a
person's actions on it, each through ``foreman.mutations``.
"""

from __future__ import annotations

from typing import Any

from ..definitions.gate_steps import (
    blocked_kind,
)
from ..definitions.layers import project_definitions
from ..definitions.roles import RoleLoadError
from ..definitions.workflows import WorkflowLoadError
from ..domain.guidance import guidance_notes
from ..domain.models import (
    Event,
    Task,
)
from ..domain.policy import PolicyMatrix, describe_resolution
from ..mutations import MutationError
from .base import Service
from .errors import (
    ActionFailedError,
    InvalidRequestError,
    NotFoundError,
)
from .views import task_source
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
        "judged_by": evidence.judged_by,
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
        "criteria_checklist": [dict(item) for item in evidence.criteria_checklist],
        "changed_files": list(evidence.changed_files),
        "branch_diff_stat": evidence.branch_diff_stat,
        "builtin_test_passed": evidence.builtin_test_passed,
        "builtin_test_detail": evidence.builtin_test_detail,
        "failure_reasons": list(evidence.failure_reasons),
        "built_at": evidence.built_at,
    }


class TaskService(Service):
    """Tasks: one task as its page shows it, creating, editing, and a person's actions on it."""

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

        runs_data = []
        for run in self.store.list_runs(task_id=task_id):
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
            "acceptance_criteria": task.acceptance_criteria,
            "workflow_current_step": task.workflow_current_step,
            "step_visit_counts": task.step_visit_counts or {},
            "depends_on_task_ids": task.depends_on_task_ids or [],
            "dependencies": self._dependencies(task),
            "complexity": task.complexity,
            "executor_overrides": task.executor_overrides or {},
            "awaiting_human_gate": self._at_human_gate(task, gates),
            "gate_policy": self._gate_policy(task, gates),
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
        complexity: str | None = None,
        depends_on: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create one task in a sprint.

        Mirrors the ``foreman task add`` CLI surface: optional ``description``,
        ``complexity`` (``small``/``medium``/``large``), and ``depends_on`` task
        ids (validated to exist in the same project).
        """

        sprint = self._require_sprint(sprint_id)
        try:
            task = self._mutations().add_task(
                sprint,
                title=title,
                task_type=task_type,
                acceptance_criteria=acceptance_criteria,
                description=description,
                complexity=complexity,
                depends_on=depends_on or (),
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
            "complexity": task.complexity,
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

    def approve_task(self, task_id: str) -> dict[str, Any]:
        """Resume one human gate with an approval outcome."""

        return self._decide_human_gate(task_id, outcome="approve", note=None)

    def deny_task(self, task_id: str, *, note: str | None = None) -> dict[str, Any]:
        """Resume one human gate with a denial outcome."""

        return self._decide_human_gate(task_id, outcome="deny", note=note)

    def _decide_human_gate(
        self, task_id: str, *, outcome: str, note: str | None
    ) -> dict[str, Any]:
        """Record a gate decision and leave the work to the project's engine.

        The web process never runs workflow steps: it holds neither the
        project's engine lock nor a task lease, and an agent step would block
        every other request for as long as it ran. The task is left at the
        step the decision leads to; a resident engine wakes on the change.
        """

        task = self._require_task(task_id)
        try:
            result = self._mutations().decide_gate(task, outcome, note)
        except MutationError as exc:
            raise ActionFailedError(f"Failed to {outcome}: {exc}") from exc
        resident = self.store.get_engine_lock(task.project_id) is not None
        return {
            "status": "approved" if outcome == "approve" else "denied",
            "task_id": task_id,
            "next_step": result.next_step,
            "deferred": result.deferred,
            "engine_resident": resident,
            "message": (
                f"Decision recorded. The engine continues from `{result.next_step}`."
                if resident
                else (
                    f"Decision recorded. No engine is running, so the task waits at "
                    f"`{result.next_step}` until you press Run."
                )
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
