"""Dashboard service layer for Foreman."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable

from .models import Event, Sprint, SprintStatus, Task
from .orchestrator import ForemanOrchestrator, OrchestratorError
from .store import ForemanStore

_VALID_SPRINT_TRANSITIONS: dict[str, tuple[SprintStatus, ...]] = {
    "planned": ("active", "cancelled"),
    "active": ("completed", "cancelled"),
    "completed": (),
    "cancelled": (),
}


ACTIVITY_EVENT_LIMIT = 50
STREAM_BATCH_LIMIT = 100
STREAM_HEARTBEAT_SECONDS = 10.0
STREAM_POLL_INTERVAL_SECONDS = 0.5


class DashboardServiceError(Exception):
    """Base error for dashboard service failures."""


class DashboardNotFoundError(DashboardServiceError):
    """Raised when one requested dashboard resource does not exist."""


class DashboardValidationError(DashboardServiceError):
    """Raised when one dashboard request payload is invalid."""


class DashboardActionError(DashboardServiceError):
    """Raised when one dashboard action cannot be completed."""


def _stable_slug(text: str) -> str:
    """Return a filesystem-safe ASCII slug from arbitrary text."""
    normalized = unicodedata.normalize("NFKD", text.strip().lower())
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug[:48] or "untitled"


class DashboardService:
    """Store-backed dashboard service used by FastAPI transport and UI clients."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self._now = now_factory or (lambda: datetime.now(timezone.utc))

    def list_projects(self) -> dict[str, Any]:
        """Return the project summary collection used by the dashboard landing screen."""

        result = []
        for project in self.store.list_projects():
            active_sprint = self.store.get_active_sprint(project.id)
            result.append(
                {
                    "id": project.id,
                    "name": project.name,
                    "workflow_id": project.workflow_id,
                    "status": self.get_project_status(project.id),
                    "active_sprint": (
                        {
                            "id": active_sprint.id,
                            "title": active_sprint.title,
                        }
                        if active_sprint is not None
                        else None
                    ),
                    "task_counts": self.store.task_counts(project_id=project.id),
                    "totals": self.store.run_totals(project_id=project.id),
                }
            )
        return {"projects": result}

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Return one project detail payload."""

        project = self.store.get_project(project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")
        return {
            "id": project.id,
            "name": project.name,
            "workflow_id": project.workflow_id,
            "default_branch": project.default_branch,
            "repo_path": project.repo_path,
            "spec_path": project.spec_path,
            "methodology": project.methodology,
        }

    def get_project_settings(self, project_id: str) -> dict[str, Any]:
        """Return settings for one project."""

        project = self.store.get_project(project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")
        return {
            "project_id": project.id,
            "workflow_id": project.workflow_id,
            "default_branch": project.default_branch,
            "spec_path": project.spec_path or "",
            "settings": dict(project.settings),
        }

    def update_project_settings(
        self,
        project_id: str,
        *,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply one partial settings update and return the current state."""

        project = self.store.get_project(project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")

        allowed_top_level = {"workflow_id", "default_branch", "spec_path"}
        for key in updates:
            if key == "settings":
                continue
            if key not in allowed_top_level:
                raise DashboardValidationError(f"Unknown setting: {key}")

        settings_updates = updates.get("settings")
        if settings_updates is not None:
            if not isinstance(settings_updates, dict):
                raise DashboardValidationError("Settings must be a JSON object.")
            project.settings.update(settings_updates)

        if "workflow_id" in updates:
            project.workflow_id = str(updates["workflow_id"])
        if "default_branch" in updates:
            project.default_branch = str(updates["default_branch"])
        if "spec_path" in updates:
            project.spec_path = str(updates["spec_path"])

        project.updated_at = self._now().isoformat()
        self.store.save_project(project)
        return self.get_project_settings(project_id)

    def list_project_sprints(self, project_id: str) -> dict[str, Any]:
        """Return sprint summaries for one project."""

        result = []
        for sprint in self.store.list_sprints(project_id):
            task_counts = self.store.task_counts(sprint_id=sprint.id)
            result.append(
                {
                    "id": sprint.id,
                    "title": sprint.title,
                    "goal": sprint.goal,
                    "status": sprint.status,
                    "task_counts": {
                        **task_counts,
                        "total": sum(task_counts.values()),
                    },
                    "totals": self.store.run_totals(sprint_id=sprint.id),
                }
            )
        return {"sprints": result}

    def get_sprint(self, sprint_id: str) -> dict[str, Any]:
        """Return one sprint summary payload."""

        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise DashboardNotFoundError(f"Sprint not found: {sprint_id}")
        return {
            "id": sprint.id,
            "title": sprint.title,
            "goal": sprint.goal,
            "status": sprint.status,
            "task_counts": self.store.task_counts(sprint_id=sprint.id),
            "totals": self.store.run_totals(sprint_id=sprint.id),
        }

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
            raise DashboardNotFoundError(f"Project not found: {project_id}")
        if not title.strip():
            raise DashboardValidationError("Sprint title is required.")

        from .models import TASK_TYPES

        sprints = self.store.list_sprints(project_id)
        sprint_id = f"sprint-{_stable_slug(title)}"
        suffix = 2
        while self.store.get_sprint(sprint_id) is not None:
            sprint_id = f"sprint-{_stable_slug(title)}-{suffix}"
            suffix += 1

        now = self._now().isoformat()
        sprint = Sprint(
            id=sprint_id,
            project_id=project_id,
            title=title.strip(),
            goal=goal.strip() if goal else None,
            status="planned",
            order_index=max((s.order_index for s in sprints), default=-1) + 1,
            created_at=now,
        )
        self.store.save_sprint(sprint)

        created_tasks = []
        for i, task_data in enumerate(initial_tasks or []):
            task_title = str(task_data.get("title", "")).strip()
            if not task_title:
                continue
            task_type = str(task_data.get("task_type", "feature"))
            if task_type not in TASK_TYPES:
                task_type = "feature"
            task_id = f"task-{_stable_slug(task_title)}"
            dedup = 2
            while self.store.get_task(task_id) is not None:
                task_id = f"task-{_stable_slug(task_title)}-{dedup}"
                dedup += 1
            task = Task(
                id=task_id,
                sprint_id=sprint_id,
                project_id=project_id,
                title=task_title,
                task_type=task_type,
                order_index=i,
                created_by="human",
                created_at=now,
            )
            self.store.save_task(task)
            created_tasks.append({"id": task.id, "title": task.title, "task_type": task.task_type})

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
        result = []
        for task in self.store.list_tasks(sprint_id=sprint_id):
            metrics = task_totals.get(task.id, {})
            result.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "task_type": task.task_type,
                    "priority": task.priority,
                    "branch_name": task.branch_name,
                    "assigned_role": task.assigned_role,
                    "blocked_reason": task.blocked_reason,
                    "acceptance_criteria": task.acceptance_criteria,
                    "totals": {
                        "total_token_count": metrics.get("total_token_count", 0),
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
    ) -> dict[str, Any]:
        """Return the sprint activity batch payload.

        With no cursor: returns the most recent ``limit`` events.
        With ``after_event_id``: returns events newer than that cursor (SSE).
        With ``before_event_id``: returns events older than that cursor (load-more).
        """

        if after_event_id:
            events = self.store.list_sprint_events(
                sprint_id,
                after_event_id=after_event_id,
                limit=limit,
            )
        elif before_event_id:
            events = self.store.list_sprint_events(
                sprint_id,
                before_event_id=before_event_id,
                limit=limit,
            )
        else:
            events = self.store.list_recent_sprint_events(sprint_id, limit=limit)
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

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Return one task detail payload including run history."""

        task = self.store.get_task(task_id)
        if task is None:
            raise DashboardNotFoundError(f"Task not found: {task_id}")

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
                    "cost_usd": run.cost_usd,
                    "duration_ms": run.duration_ms,
                    "created_at": run.created_at,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "model": run.model,
                    "session_id": run.session_id,
                    "branch_name": run.branch_name,
                }
            )

        return {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "task_type": task.task_type,
            "description": task.description,
            "priority": task.priority,
            "branch_name": task.branch_name,
            "assigned_role": task.assigned_role,
            "created_by": task.created_by,
            "blocked_reason": task.blocked_reason,
            "acceptance_criteria": task.acceptance_criteria,
            "workflow_current_step": task.workflow_current_step,
            "step_visit_counts": task.step_visit_counts or {},
            "depends_on_task_ids": task.depends_on_task_ids or [],
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
    ) -> dict[str, Any]:
        """Create one task in a sprint."""

        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise DashboardNotFoundError(f"Sprint not found: {sprint_id}")
        if not title.strip():
            raise DashboardValidationError("Task title is required.")

        from .models import TASK_TYPES

        if task_type not in TASK_TYPES:
            raise DashboardValidationError(
                f"Unsupported task type: {task_type}. "
                f"Expected one of: {', '.join(TASK_TYPES)}."
            )

        existing_tasks = self.store.list_tasks(sprint_id=sprint_id)
        task_id = f"task-{_stable_slug(title)}"
        suffix = 2
        while self.store.get_task(task_id) is not None:
            task_id = f"task-{_stable_slug(title)}-{suffix}"
            suffix += 1

        now = self._now().isoformat()
        task = Task(
            id=task_id,
            sprint_id=sprint_id,
            project_id=sprint.project_id,
            title=title.strip(),
            task_type=task_type,
            acceptance_criteria=acceptance_criteria.strip() if acceptance_criteria else None,
            order_index=max((t.order_index for t in existing_tasks), default=-1) + 1,
            created_by="human",
            created_at=now,
        )
        self.store.save_task(task)
        return {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "task_type": task.task_type,
            "acceptance_criteria": task.acceptance_criteria,
            "order_index": task.order_index,
            "created_at": task.created_at,
        }

    def transition_sprint(self, sprint_id: str, *, target_status: str) -> dict[str, Any]:
        """Transition one sprint to a new lifecycle status."""

        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise DashboardNotFoundError(f"Sprint not found: {sprint_id}")

        allowed = _VALID_SPRINT_TRANSITIONS.get(sprint.status, ())
        if target_status not in allowed:
            raise DashboardValidationError(
                f"Cannot transition sprint from '{sprint.status}' to '{target_status}'. "
                f"Allowed: {list(allowed) or 'none'}."
            )

        now = self._now().isoformat()
        sprint.status = target_status  # type: ignore[assignment]
        if target_status == "active" and sprint.started_at is None:
            sprint.started_at = now
        if target_status in ("completed", "cancelled"):
            sprint.completed_at = now

        self.store.save_sprint(sprint)
        return {
            "id": sprint.id,
            "status": sprint.status,
            "started_at": sprint.started_at,
            "completed_at": sprint.completed_at,
        }

    def update_task_fields(self, task_id: str, *, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply allowed field updates to one task and return its detail payload."""

        from .models import TASK_TYPES

        task = self._require_task(task_id)
        allowed_fields = {"title", "task_type", "acceptance_criteria", "description", "priority"}
        unknown = set(updates) - allowed_fields
        if unknown:
            raise DashboardValidationError(f"Unknown task fields: {sorted(unknown)}")

        if "title" in updates:
            value = str(updates["title"]).strip()
            if not value:
                raise DashboardValidationError("Task title cannot be empty.")
            task.title = value
        if "task_type" in updates:
            value = str(updates["task_type"])
            if value not in TASK_TYPES:
                raise DashboardValidationError(
                    f"Unsupported task type: {value}. Expected one of: {', '.join(TASK_TYPES)}."
                )
            task.task_type = value  # type: ignore[assignment]
        if "acceptance_criteria" in updates:
            value = updates["acceptance_criteria"]
            task.acceptance_criteria = str(value).strip() if value else None
        if "description" in updates:
            value = updates["description"]
            task.description = str(value).strip() if value is not None else None
        if "priority" in updates:
            try:
                task.priority = int(updates["priority"])
            except (TypeError, ValueError) as exc:
                raise DashboardValidationError("Priority must be an integer.") from exc

        self.store.save_task(task)
        return self.get_task(task_id)

    def update_sprint_fields(self, sprint_id: str, *, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply non-lifecycle field updates to one sprint (title, goal)."""

        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise DashboardNotFoundError(f"Sprint not found: {sprint_id}")

        allowed_fields = {"title", "goal"}
        unknown = set(updates) - allowed_fields
        if unknown:
            raise DashboardValidationError(f"Unknown sprint fields: {sorted(unknown)}")
        if not updates:
            raise DashboardValidationError("No fields provided for update.")

        if "title" in updates:
            value = str(updates["title"]).strip()
            if not value:
                raise DashboardValidationError("Sprint title cannot be empty.")
            sprint.title = value
        if "goal" in updates:
            value = updates["goal"]
            sprint.goal = str(value).strip() if value else None

        self.store.save_sprint(sprint)
        return {
            "id": sprint.id,
            "title": sprint.title,
            "goal": sprint.goal,
            "status": sprint.status,
        }

    def stop_agent(self, project_id: str) -> dict[str, Any]:
        """Block all in-progress tasks in the active sprint to signal a stop request."""

        project = self.store.get_project(project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")

        active_sprint = self.store.get_active_sprint(project_id)
        if active_sprint is None:
            return {"stopped": 0, "project_id": project_id}

        now = self._now()
        tasks = self.store.list_tasks(sprint_id=active_sprint.id)
        stopped = 0
        for task in tasks:
            if task.status != "in_progress":
                continue
            task.status = "blocked"
            task.blocked_reason = "Stop requested from dashboard."
            self.store.save_task(task)

            runs = self.store.list_runs(task_id=task.id)
            event = Event(
                id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-stop-{task.id[:8]}",
                run_id=runs[0].id if runs else "none",
                task_id=task.id,
                project_id=project_id,
                event_type="human.stop_requested",
                timestamp=now.isoformat(),
                role_id="human",
                payload={"reason": "Stop requested from dashboard."},
            )
            self.store.save_event(event)
            stopped += 1

        return {
            "stopped": stopped,
            "project_id": project_id,
            "sprint_id": active_sprint.id,
        }

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        """Cancel one task that is not already done or cancelled."""

        task = self._require_task(task_id)
        if task.status in ("done", "cancelled"):
            raise DashboardValidationError(
                f"Cannot cancel a task with status '{task.status}'."
            )
        task.status = "cancelled"
        self.store.save_task(task)
        return {"status": "cancelled", "task_id": task_id}

    def approve_task(self, task_id: str) -> dict[str, Any]:
        """Resume one human gate with an approval outcome."""

        self._require_task(task_id)
        orchestrator = ForemanOrchestrator(self.store)
        try:
            result = orchestrator.resume_human_gate(task_id, outcome="approve")
        except OrchestratorError as exc:
            raise DashboardActionError(f"Failed to approve: {exc}") from exc
        return {
            "status": "approved",
            "task_id": task_id,
            "next_step": result.next_step,
            "deferred": result.deferred,
        }

    def deny_task(self, task_id: str, *, note: str | None = None) -> dict[str, Any]:
        """Resume one human gate with a denial outcome."""

        self._require_task(task_id)
        orchestrator = ForemanOrchestrator(self.store)
        try:
            result = orchestrator.resume_human_gate(task_id, outcome="deny", note=note)
        except OrchestratorError as exc:
            raise DashboardActionError(f"Failed to deny: {exc}") from exc
        return {
            "status": "denied",
            "task_id": task_id,
            "next_step": result.next_step,
            "deferred": result.deferred,
        }

    def create_human_message(self, task_id: str, *, text: str) -> dict[str, Any]:
        """Persist one human guidance message for the selected task."""

        task = self._require_task(task_id)
        normalized_text = text.strip()
        if not normalized_text:
            raise DashboardValidationError("Message text required")

        runs = self.store.list_runs(task_id=task_id)
        now = self._now()
        event = Event(
            id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-{task_id[:8]}",
            run_id=runs[0].id if runs else "none",
            task_id=task_id,
            project_id=task.project_id,
            event_type="human.message",
            timestamp=now.isoformat(),
            role_id="human",
            payload={"text": normalized_text},
        )
        self.store.save_event(event)
        return {
            "status": "sent",
            "event_id": event.id,
            "task_id": task_id,
        }

    def get_project_status(self, project_id: str) -> str:
        """Derive one project status from its task states."""

        tasks = self.store.list_tasks(project_id=project_id)
        if any(task.status == "in_progress" for task in tasks):
            return "running"
        if any(task.status == "blocked" for task in tasks):
            return "blocked"
        return "idle"

    def _require_task(self, task_id: str):
        task = self.store.get_task(task_id)
        if task is None:
            raise DashboardNotFoundError(f"Task not found: {task_id}")
        return task

    @staticmethod
    def _serialize_event(event: Event) -> dict[str, Any]:
        return {
            "id": event.id,
            "task_id": event.task_id,
            "project_id": event.project_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "role_id": event.role_id,
            "payload": event.payload,
        }
