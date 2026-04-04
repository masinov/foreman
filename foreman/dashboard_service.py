"""Dashboard service layer for Foreman."""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .models import AUTONOMY_LEVELS, DecisionGate, Event, Project, Run, Sprint, SprintStatus, Task
from .orchestrator import ForemanOrchestrator, OrchestratorError
from .scaffold import generate_project_id
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


_ALLOWED_ROLE_FIELDS: frozenset[str] = frozenset(
    {"backend", "model", "permission_mode", "timeout_minutes", "max_cost_usd"}
)


def _validate_role_updates(updates: dict[str, Any]) -> None:
    """Raise DashboardValidationError when any role field value is invalid."""

    for field_name in ("backend", "model", "permission_mode"):
        if field_name in updates and not isinstance(updates[field_name], str):
            raise DashboardValidationError(f"'{field_name}' must be a string.")

    if "timeout_minutes" in updates:
        value = updates["timeout_minutes"]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise DashboardValidationError("'timeout_minutes' must be a positive integer.")

    if "max_cost_usd" in updates:
        value = updates["max_cost_usd"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
            raise DashboardValidationError("'max_cost_usd' must be a positive number.")


def _serialize_role(role: "Any") -> dict[str, Any]:
    """Serialize one RoleDefinition to a JSON-friendly dict."""

    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "backend": role.agent.backend,
        "model": role.agent.model,
        "permission_mode": role.agent.permission_mode,
        "session_persistence": role.agent.session_persistence,
        "timeout_minutes": role.completion.timeout_minutes,
        "max_cost_usd": role.completion.max_cost_usd,
        "source_path": str(role.source_path),
    }


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
        self._running_procs: dict[str, subprocess.Popen[bytes]] = {}

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
            "autonomy_level": project.autonomy_level,
            "totals": self.store.run_totals(project_id=project_id),
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
            "autonomy_level": project.autonomy_level,
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

        allowed_top_level = {"workflow_id", "default_branch", "spec_path", "autonomy_level"}
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
        if "autonomy_level" in updates:
            value = str(updates["autonomy_level"])
            if value not in AUTONOMY_LEVELS:
                raise DashboardValidationError(
                    f"Invalid autonomy_level: '{value}'. "
                    f"Expected one of: {', '.join(AUTONOMY_LEVELS)}."
                )
            project.autonomy_level = value  # type: ignore[assignment]

        project.updated_at = self._now().isoformat()
        self.store.save_project(project)
        return self.get_project_settings(project_id)

    def create_project(
        self,
        *,
        name: str,
        repo_path: str,
        workflow_id: str = "development",
    ) -> dict[str, Any]:
        """Register a new project record in the dashboard."""

        name = name.strip()
        if not name:
            raise DashboardValidationError("Project name cannot be empty.")
        repo_path = repo_path.strip()
        if not repo_path:
            raise DashboardValidationError("Repo path cannot be empty.")
        workflow_id = (workflow_id or "development").strip()
        if not workflow_id:
            raise DashboardValidationError("Workflow ID cannot be empty.")

        base_id = generate_project_id(name, repo_path)
        project_id = base_id
        suffix = 2
        while self.store.get_project(project_id) is not None:
            project_id = f"{base_id}-{suffix}"
            suffix += 1

        project = Project(
            id=project_id,
            name=name,
            repo_path=repo_path,
            workflow_id=workflow_id,
        )
        self.store.save_project(project)
        return {
            "id": project.id,
            "name": project.name,
            "repo_path": project.repo_path,
            "workflow_id": project.workflow_id,
            "status": "idle",
        }

    def start_agent(
        self,
        project_id: str,
        *,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Spawn a ``foreman run`` subprocess for the given project."""

        project = self.store.get_project(project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")

        existing = self._running_procs.get(project_id)
        if existing is not None and existing.poll() is None:
            raise DashboardValidationError(
                f"Agent is already running for project {project_id}."
            )

        foreman_bin = str(Path(sys.executable).parent / "foreman")
        cmd = [foreman_bin, "run", "--project", project_id, "--db", self.store.db_path]
        if task_id is not None:
            cmd.extend(["--task", task_id])

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._running_procs[project_id] = proc

        def _cleanup() -> None:
            proc.wait()
            if self._running_procs.get(project_id) is proc:
                self._running_procs.pop(project_id, None)

        threading.Thread(target=_cleanup, daemon=True).start()

        return {"started": True, "project_id": project_id}

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
                    "order_index": sprint.order_index,
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
                    "workflow_current_step": task.workflow_current_step,
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

        if target_status == "active":
            existing_active = self.store.get_active_sprint(sprint.project_id)
            if existing_active is not None and existing_active.id != sprint.id:
                raise DashboardValidationError(
                    f"Sprint '{existing_active.title}' is already active. "
                    "Complete or cancel it before activating another sprint."
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
        """Apply allowed field updates to one task and return its detail payload.

        Emits a ``human.task_edited`` event when the task is in-progress or
        blocked so the change is visible in the activity stream and the agent
        can account for it on its next run.
        """

        from .models import TASK_TYPES

        task = self._require_task(task_id)
        allowed_fields = {"title", "task_type", "acceptance_criteria", "description", "priority"}
        unknown = set(updates) - allowed_fields
        if unknown:
            raise DashboardValidationError(f"Unknown task fields: {sorted(unknown)}")

        changed: dict[str, Any] = {}

        if "title" in updates:
            value = str(updates["title"]).strip()
            if not value:
                raise DashboardValidationError("Task title cannot be empty.")
            if value != task.title:
                changed["title"] = value
            task.title = value
        if "task_type" in updates:
            value = str(updates["task_type"])
            if value not in TASK_TYPES:
                raise DashboardValidationError(
                    f"Unsupported task type: {value}. Expected one of: {', '.join(TASK_TYPES)}."
                )
            if value != task.task_type:
                changed["task_type"] = value
            task.task_type = value  # type: ignore[assignment]
        if "acceptance_criteria" in updates:
            value = updates["acceptance_criteria"]
            normalised = str(value).strip() if value else None
            if normalised != task.acceptance_criteria:
                changed["acceptance_criteria"] = normalised
            task.acceptance_criteria = normalised
        if "description" in updates:
            value = updates["description"]
            normalised = str(value).strip() if value is not None else None
            if normalised != task.description:
                changed["description"] = normalised
            task.description = normalised
        if "priority" in updates:
            try:
                int_value = int(updates["priority"])
            except (TypeError, ValueError) as exc:
                raise DashboardValidationError("Priority must be an integer.") from exc
            if int_value != task.priority:
                changed["priority"] = int_value
            task.priority = int_value

        self.store.save_task(task)

        if changed and task.status in {"in_progress", "blocked"}:
            now = self._now()
            now_text = now.isoformat()
            runs = self.store.list_runs(task_id=task_id)
            if runs:
                run_id = runs[0].id
            else:
                synthetic_run = Run(
                    id=f"run-edit-{now.strftime('%Y%m%d%H%M%S%f')}-{task_id[:8]}",
                    task_id=task_id,
                    project_id=task.project_id,
                    role_id="human",
                    workflow_step="edit",
                    agent_backend="dashboard",
                    status="completed",
                    outcome="edit",
                    started_at=now_text,
                    completed_at=now_text,
                    created_at=now_text,
                )
                self.store.save_run(synthetic_run)
                run_id = synthetic_run.id
            event = Event(
                id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-edit-{task_id[:8]}",
                run_id=run_id,
                task_id=task_id,
                project_id=task.project_id,
                event_type="human.task_edited",
                timestamp=now_text,
                role_id="human",
                payload={"changed_fields": changed},
            )
            self.store.save_event(event)

        return self.get_task(task_id)

    def update_sprint_fields(self, sprint_id: str, *, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply non-lifecycle field updates to one sprint (title, goal)."""

        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise DashboardNotFoundError(f"Sprint not found: {sprint_id}")

        allowed_fields = {"title", "goal", "order_index"}
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
        if "order_index" in updates:
            sprint.order_index = int(updates["order_index"])

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

    def stop_task(self, task_id: str) -> dict[str, Any]:
        """Block one in-progress task to signal a stop request."""

        task = self._require_task(task_id)
        if task.status != "in_progress":
            raise DashboardValidationError(
                f"Cannot stop a task with status '{task.status}'; only in_progress tasks can be stopped."
            )
        task.status = "blocked"
        task.blocked_reason = "Stop requested from dashboard."
        self.store.save_task(task)

        now = self._now()
        now_text = now.isoformat()
        runs = self.store.list_runs(task_id=task.id)
        if runs:
            run_id = runs[0].id
        else:
            synthetic_run = Run(
                id=f"run-stop-{now.strftime('%Y%m%d%H%M%S%f')}-{task.id[:8]}",
                task_id=task.id,
                project_id=task.project_id,
                role_id="human",
                workflow_step="stop",
                agent_backend="dashboard",
                status="completed",
                outcome="stopped",
                started_at=now_text,
                completed_at=now_text,
                created_at=now_text,
            )
            self.store.save_run(synthetic_run)
            run_id = synthetic_run.id
        event = Event(
            id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-stop-{task.id[:8]}",
            run_id=run_id,
            task_id=task.id,
            project_id=task.project_id,
            event_type="human.stop_requested",
            timestamp=now_text,
            role_id="human",
            payload={"reason": "Stop requested from dashboard."},
        )
        self.store.save_event(event)
        return {"status": "blocked", "task_id": task_id}

    def delete_sprint(self, sprint_id: str) -> dict[str, Any]:
        """Delete a sprint and all its tasks, runs, and events."""

        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise DashboardNotFoundError(f"Sprint not found: {sprint_id}")
        project_id = sprint.project_id
        self.store.delete_sprint(sprint_id)
        return {"ok": "deleted", "sprint_id": sprint_id, "project_id": project_id}

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

    def list_roles(self) -> dict[str, Any]:
        """Return all available role definitions."""

        from .roles import RoleLoadError, load_roles

        try:
            roles = load_roles()
        except RoleLoadError as exc:
            raise DashboardActionError(f"Failed to load roles: {exc}") from exc
        return {"roles": [_serialize_role(role) for role in roles.values()]}

    def update_role(self, role_id: str, *, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply allowed field updates to one role TOML file and return the updated role.

        Allowed fields: backend, model, permission_mode, timeout_minutes, max_cost_usd.
        Unknown role returns DashboardNotFoundError; validation failures raise
        DashboardValidationError.
        """

        from .roles import RoleLoadError, load_role, load_roles

        try:
            roles = load_roles()
        except RoleLoadError as exc:
            raise DashboardActionError(f"Failed to load roles: {exc}") from exc

        if role_id not in roles:
            raise DashboardNotFoundError(f"Role not found: {role_id}")

        unknown = set(updates) - _ALLOWED_ROLE_FIELDS
        if unknown:
            raise DashboardValidationError(
                f"Unknown role fields: {', '.join(sorted(unknown))}"
            )

        if not updates:
            return _serialize_role(roles[role_id])

        _validate_role_updates(updates)

        import tomlkit

        role = roles[role_id]
        with open(role.source_path, encoding="utf-8") as fh:
            doc = tomlkit.load(fh)

        for key, value in updates.items():
            if key in ("backend", "model", "permission_mode"):
                doc["agent"][key] = value
            elif key == "timeout_minutes":
                doc["completion"]["timeout_minutes"] = int(value)
            elif key == "max_cost_usd":
                doc["completion"]["max_cost_usd"] = float(value)

        with open(role.source_path, "w", encoding="utf-8") as fh:
            tomlkit.dump(doc, fh)

        try:
            updated_role = load_role(role.source_path)
        except RoleLoadError as exc:
            raise DashboardActionError(f"Failed to reload role after update: {exc}") from exc
        return _serialize_role(updated_role)

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

    # ── Decision gates ────────────────────────────────────────────────────────

    def create_gate(
        self,
        project_id: str,
        *,
        sprint_id: str,
        conflict_description: str,
        suggested_order: list[str] | None = None,
        suggested_reason: str = "",
    ) -> dict[str, Any]:
        """Raise a new decision gate for a project."""

        project = self.store.get_project(project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")
        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise DashboardNotFoundError(f"Sprint not found: {sprint_id}")
        if sprint.project_id != project_id:
            raise DashboardValidationError("Sprint does not belong to this project.")
        if not conflict_description.strip():
            raise DashboardValidationError("conflict_description cannot be empty.")

        now = self._now()
        gate_id = f"gate-{now.strftime('%Y%m%d%H%M%S%f')}-{project_id[:8]}"
        gate = DecisionGate(
            id=gate_id,
            project_id=project_id,
            sprint_id=sprint_id,
            conflict_description=conflict_description.strip(),
            suggested_order=suggested_order or [],
            suggested_reason=suggested_reason.strip(),
            raised_at=now.isoformat(),
        )
        self.store.save_decision_gate(gate)
        return self._serialize_gate(gate)

    def list_gates(self, project_id: str, *, status: str | None = None) -> dict[str, Any]:
        """List decision gates for a project."""

        project = self.store.get_project(project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")
        gates = self.store.list_decision_gates(project_id, status=status)
        return {"gates": [self._serialize_gate(g) for g in gates]}

    def resolve_gate(self, gate_id: str, *, resolution: str, resolved_by: str = "human") -> dict[str, Any]:
        """Resolve a pending decision gate.

        resolution must be one of: accepted, rejected, dismissed.
        - accepted: applies suggested_order by rewriting order_index values on the sprints.
        - rejected / dismissed: no sprint reorder; gate is closed.
        """

        gate = self.store.get_decision_gate(gate_id)
        if gate is None:
            raise DashboardNotFoundError(f"Decision gate not found: {gate_id}")
        if gate.status != "pending":
            raise DashboardValidationError(
                f"Gate is already resolved (status: {gate.status})."
            )
        valid = ("accepted", "rejected", "dismissed")
        if resolution not in valid:
            raise DashboardValidationError(
                f"Invalid resolution '{resolution}'. Expected one of: {', '.join(valid)}."
            )

        now = self._now()
        gate.status = resolution  # type: ignore[assignment]
        gate.resolved_at = now.isoformat()
        gate.resolved_by = resolved_by

        if resolution == "accepted" and gate.suggested_order:
            for idx, sprint_id in enumerate(gate.suggested_order):
                sprint = self.store.get_sprint(sprint_id)
                if sprint is not None and sprint.project_id == gate.project_id:
                    sprint.order_index = idx
                    self.store.save_sprint(sprint)

        self.store.save_decision_gate(gate)
        return self._serialize_gate(gate)

    @staticmethod
    def _serialize_gate(gate: DecisionGate) -> dict[str, Any]:
        return {
            "id": gate.id,
            "project_id": gate.project_id,
            "sprint_id": gate.sprint_id,
            "conflict_description": gate.conflict_description,
            "suggested_order": gate.suggested_order,
            "suggested_reason": gate.suggested_reason,
            "status": gate.status,
            "raised_at": gate.raised_at,
            "resolved_at": gate.resolved_at,
            "resolved_by": gate.resolved_by,
        }

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
