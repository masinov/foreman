"""Sprints: the list, one sprint, its board and its activity, and its lifecycle.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..definitions.gate_steps import (
    blocked_kind,
)
from ..domain.models import (
    TASK_TYPES,
    Sprint,
    sprint_ready_to_finish,
)
from ..engine.limits import resolve_project_settings
from ..engine.selection import pulled_task_ids
from ..mutations import MutationError
from ..store.overview import SPRINT_LIST_ORDERS, SPRINT_LIST_STATUSES
from .base import Service
from .errors import InvalidRequestError, NotFoundError
from .views import HoldReader, serialize_level_block, task_source, waits_for
from .work_status import sprint_work_status

ACTIVITY_EVENT_LIMIT = 50


STREAM_BATCH_LIMIT = 100


STREAM_HEARTBEAT_SECONDS = 10.0


# Each tick now costs one PRAGMA data_version unless the DB actually changed, so
# we can poll more responsively without hammering the full sprint-events query.
STREAM_POLL_INTERVAL_SECONDS = 0.25


def _serialize_task_checks(evidence: "Any") -> dict[str, Any] | None:
    """The completion evidence of a task, reduced to what a list row shows.

    ``tests`` and ``review`` are the evidence's own words (``passed``,
    ``failed``, ``approve``...), empty when that check did not run; ``commit``
    is the commit the evidence was built at. ``None`` when no evidence exists.
    """
    if evidence is None:
        return None
    return {
        "tests": evidence.tests_status or None,
        "review": evidence.review_outcome or None,
        "commit": evidence.head_sha or None,
    }


class SprintService(Service):
    """Sprints: the list, one sprint, its board and activity, and its lifecycle."""

    def list_project_sprints(
        self,
        project_id: str,
        *,
        statuses: Sequence[str] | None = None,
        query: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str = "queue",
    ) -> dict[str, Any]:
        """Return sprint summaries for one project.

        Without arguments every sprint is returned, as it always was.
        ``statuses`` keeps only sprints in those states, ``query`` only those
        whose title (which carries the sprint number) or id contains it, and
        ``limit``/``offset`` select a page. ``total`` counts every sprint that
        matches, before paging. ``order`` is ``queue`` (the order they run in)
        or ``recent`` (most recently finished first, for finished sprints).
        """

        if order not in SPRINT_LIST_ORDERS:
            raise InvalidRequestError(
                f"order: unknown {order}; expected {', '.join(SPRINT_LIST_ORDERS)}."
            )

        unknown = sorted(set(statuses or ()) - set(SPRINT_LIST_STATUSES))
        if unknown:
            raise InvalidRequestError(
                f"status: unknown {', '.join(unknown)}; expected "
                f"{', '.join(SPRINT_LIST_STATUSES)}."
            )
        sprints, total = self.store.page_project_sprints(
            project_id,
            statuses=statuses,
            query=(query or "").strip() or None,
            limit=limit,
            offset=offset,
            order=order,
        )
        result = []
        for sprint in sprints:
            task_counts = self.store.task_counts(sprint_id=sprint.id)
            entry: dict[str, Any] = {
                "id": sprint.id,
                "project_id": sprint.project_id,
                "title": sprint.title,
                "goal": sprint.goal,
                "status": sprint.status,
                "order_index": sprint.order_index,
                "started_at": sprint.started_at,
                "completed_at": sprint.completed_at,
                "task_counts": {
                    **task_counts,
                    "total": sum(task_counts.values()),
                },
                "totals": self.store.run_totals(sprint_id=sprint.id),
            }
            if sprint.status == "active":
                entry["tasks"] = [
                    {"id": t.id, "task_key": t.task_key, "title": t.title, "status": t.status, "task_type": t.task_type}
                    for t in self.store.list_tasks(sprint_id=sprint.id)
                ]
            result.append(entry)
        return {"sprints": result, "total": total}

    def get_sprint(self, sprint_id: str) -> dict[str, Any]:
        """Return one sprint summary payload."""

        sprint = self._require_sprint(sprint_id)

        project = self.store.get_project(sprint.project_id)
        counts = self.store.task_counts(sprint_id=sprint.id)
        return {
            "id": sprint.id,
            "project_id": sprint.project_id,
            "title": sprint.title,
            "goal": sprint.goal,
            "status": sprint.status,
            "started_at": sprint.started_at,
            "completed_at": sprint.completed_at,
            # The project's task selection mode: whether the engine picks its
            # own tasks instead of running only what was planned.
            "picks_own_tasks": bool(
                project and resolve_project_settings(project).task_selection_mode == "autonomous"
            ),
            # The tasks Foreman took from the backlog into this sprint on its
            # own, against the limit per sprint (ADR-0028).
            "started_by_foreman": len(pulled_task_ids(self.store, sprint)),
            "foreman_limit": resolve_project_settings(project).max_autonomous_tasks if project else None,
            "task_counts": counts,
            # Every task done or cancelled while the sprint is active: the
            # rule the engine finishes it by (ADR-0037).
            "ready_to_finish": sprint_ready_to_finish(sprint.status, counts),
            "totals": self.store.run_totals(sprint_id=sprint.id),
            "checkpoint": self._checkpoint(sprint),
            # A user's block on this sprint, and on the workspace (ADR-0043).
            "block": serialize_level_block(self.store.get_sprint_block(sprint.id)),
            "workspace_block": serialize_level_block(self.store.get_workspace_block()),
            # What its work is doing now, for the status line (ADR-0043).
            "work": sprint_work_status(
                self.store, sprint, workspace_block=self.store.get_workspace_block()
            ),
        }

    def _checkpoint(self, sprint: Sprint) -> dict[str, Any] | None:
        """The tag (and note) of the sprint's last completion, or why there is none (spec 6.4)."""

        if sprint.status != "completed":
            return None
        events = self.store.list_sprint_events(
            sprint.id, event_types=["engine.checkpoint", "engine.checkpoint_failed"]
        )
        for event in reversed(events):
            payload = event.payload
            if payload.get("sprint_id") != sprint.id or payload.get("completed_at") != sprint.completed_at:
                continue
            if event.event_type == "engine.checkpoint_failed":
                return {"tag": None, "sha": None, "note_path": None, "changelog_path": None, "problem": payload.get("reason")}
            return {
                "tag": payload.get("tag"),
                "sha": payload.get("sha"),
                "note_path": payload.get("note_path"),
                "changelog_path": payload.get("changelog_path"),
                "problem": None,
            }
        return None

    def create_sprint(
        self,
        project_id: str,
        *,
        title: str,
        goal: str | None = None,
        initial_tasks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create one sprint for a project, optionally with an initial task list."""

        project = self.store.get_project(project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {project_id}")
        if not title.strip():
            raise InvalidRequestError("Sprint title is required.")


        try:
            sprint = self._mutations().create_sprint(project, title=title, goal=goal)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        created_tasks = []
        mutations = self._mutations()
        for i, task_data in enumerate(initial_tasks or []):
            task_title = str(task_data.get("title", "")).strip()
            if not task_title:
                continue
            task_type = str(task_data.get("task_type", "feature"))
            task = mutations.add_task(
                sprint,
                title=task_title,
                task_type=task_type if task_type in TASK_TYPES else "feature",
                acceptance_criteria=str(task_data.get("acceptance_criteria") or "") or None,
                description=str(task_data.get("description") or "") or None,
                order_index=i,
            )
            created_tasks.append(
                {"id": task.id, "task_key": task.task_key, "title": task.title, "task_type": task.task_type}
            )

        return {
            "id": sprint.id,
            "title": sprint.title,
            "goal": sprint.goal,
            "status": sprint.status,
            "order_index": sprint.order_index,
            "created_at": sprint.created_at,
            "tasks_created": len(created_tasks),
        }

    def list_sprint_tasks(self, sprint_id: str) -> dict[str, Any]:
        """Return task cards for one sprint board."""

        task_totals = {
            str(row["task_id"]): row
            for row in self.store.task_run_totals(sprint_id=sprint_id)
        }
        sprint = self.store.get_sprint(sprint_id)
        project = self.store.get_project(sprint.project_id) if sprint else None
        gates = self._gate_steps(project)
        run_next = (
            self.store.run_requested_task_ids(sprint.project_id) if sprint else set()
        )
        holds = HoldReader(self.store)
        running = (
            {run.task_id for run in self.store.list_runs(project_id=sprint.project_id, status="running")}
            if sprint
            else set()
        )
        result = []
        for task in self.store.list_tasks(sprint_id=sprint_id):
            metrics = task_totals.get(task.id, {})
            result.append(
                {
                    "id": task.id,
                    "project_id": task.project_id,
                    "sprint_id": task.sprint_id,
                    "task_key": task.task_key,
                    "title": task.title,
                    "status": task.status,
                    # A "Run next" the engine has not started yet.
                    "run_next": task.id in run_next,
                    "task_type": task.task_type,
                    "priority": task.priority,
                    "branch_name": task.branch_name,
                    "assigned_role": task.assigned_role,
                    "blocked_reason": task.blocked_reason,
                    "hold": holds.hold(task),
                    "step_running": task.id in running,
                    # The unfinished tasks it waits for, by key ("Waiting · FOR-65").
                    "waits_for": waits_for(self.store, task),
                    "acceptance_criteria": task.acceptance_criteria,
                    "workflow_current_step": task.workflow_current_step,
                    "step_visit_counts": dict(task.step_visit_counts),
                    "awaiting_human_gate": self._at_human_gate(task, gates),
                    "gate_policy": self._gate_policy(task, gates),
                    "blocked_kind": blocked_kind(task, gates),
                    "executor_overrides": task.executor_overrides,
                    "source": task_source(task),
                    "checks": _serialize_task_checks(task.completion_evidence),
                    "totals": {
                        "total_token_count": metrics.get("total_token_count", 0),
                        "token_usage": metrics.get("token_usage"),
                        "total_cost_usd": metrics.get("total_cost_usd", 0.0),
                        "run_count": metrics.get("run_count", 0),
                    },
                }
            )
        return {"tasks": result}

    def list_sprint_events(
        self,
        sprint_id: str,
        *,
        limit: int = ACTIVITY_EVENT_LIMIT,
        after_event_id: str | None = None,
        before_event_id: str | None = None,
        event_types: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Return the sprint activity batch payload.

        ``event_types`` keeps only those event types (the sprint page asks for
        ``workflow.step_completed``).

        With no cursor: returns the most recent ``limit`` events.
        With ``after_event_id``: returns events newer than that cursor (SSE).
        With ``before_event_id``: returns events older than that cursor (load-more).
        """

        if after_event_id:
            events = self.store.list_sprint_events(
                sprint_id,
                after_event_id=after_event_id,
                limit=limit,
                event_types=event_types,
            )
        elif before_event_id:
            events = self.store.list_sprint_events(
                sprint_id,
                before_event_id=before_event_id,
                limit=limit,
                event_types=event_types,
            )
        else:
            events = self.store.list_recent_sprint_events(
                sprint_id, limit=limit, event_types=event_types
            )
        return {
            "events": [self._serialize_event(event) for event in events],
            "has_more": len(events) == limit,
        }

    def list_sprint_stream_messages(
        self,
        sprint_id: str,
        *,
        limit: int = STREAM_BATCH_LIMIT,
        after_event_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the incremental streaming payload batch for one sprint."""

        events = self.list_sprint_events(
            sprint_id,
            limit=limit,
            after_event_id=after_event_id,
        )["events"]
        return [
            {
                "event_id": str(event["id"]),
                "payload": {"type": "event", "event": event},
            }
            for event in events
        ]

    def list_project_stream_messages(
        self,
        project_id: str,
        *,
        limit: int = STREAM_BATCH_LIMIT,
        after_event_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the next streaming batch for a whole project.

        With a cursor: the events after it, oldest first. Without one: the
        most recent ``limit`` events, so a new listener starts with context.
        A cursor that no longer exists (its event was pruned) starts over
        from the most recent events instead of going silent.
        """

        self._require_project(project_id)
        if after_event_id and self.store.get_event(after_event_id) is not None:
            events = self.store.list_events(
                project_id=project_id, after_event_id=after_event_id, limit=limit
            )
        else:
            events = self.store.list_recent_events(project_id=project_id, limit=limit)
        return [
            {
                "event_id": event.id,
                "payload": {"type": "event", "event": self._serialize_event(event)},
            }
            for event in events
        ]

    def transition_sprint(self, sprint_id: str, *, target_status: str) -> dict[str, Any]:
        """Transition one sprint to a new lifecycle status."""

        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise NotFoundError(f"Sprint not found: {sprint_id}")
        try:
            sprint = self._mutations().transition_sprint(sprint, target_status)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return {
            "id": sprint.id,
            "status": sprint.status,
            "started_at": sprint.started_at,
            "completed_at": sprint.completed_at,
        }

    def update_sprint_fields(self, sprint_id: str, *, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply non-lifecycle field updates to one sprint (title, goal)."""

        sprint = self._require_sprint(sprint_id)
        try:
            sprint = self._mutations().edit_sprint(sprint, updates)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return {
            "id": sprint.id,
            "title": sprint.title,
            "goal": sprint.goal,
            "status": sprint.status,
        }

    def move_sprint(self, sprint_id: str, *, direction: str) -> dict[str, Any]:
        """Move a planned sprint one place up or down the queue; return the planned order."""

        sprint = self._require_sprint(sprint_id)
        try:
            sprint = self._mutations().move_sprint(sprint, direction)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        planned = [
            entry.id for entry in self.store.list_sprints(sprint.project_id) if entry.status == "planned"
        ]
        return {"id": sprint.id, "order_index": sprint.order_index, "planned_order": planned}

    def delete_sprint(self, sprint_id: str) -> dict[str, Any]:
        """Delete a sprint and all its tasks, runs, and events."""

        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise NotFoundError(f"Sprint not found: {sprint_id}")
        project_id = sprint.project_id
        try:
            self._mutations().delete_sprint(sprint)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return {"ok": "deleted", "sprint_id": sprint_id, "project_id": project_id}
