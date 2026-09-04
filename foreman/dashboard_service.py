"""Dashboard service layer for Foreman.

The service reads and writes SQLite (ADR-0002) and holds no process handles.
Steering the engine is the ``engine_commands`` table's job: Run enqueues a
``resume``, Pause enqueues a ``pause``, and a task Stop enqueues a
``stop_task``. The one exception is the single-machine bootstrap — when no
engine is resident there is nothing to send a command to, so the service
spawns a detached ``foreman serve`` through an injectable spawner and then
talks to it like any other resident engine.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .engine_control import (
    EngineStateView,
    ServeSpawner,
    WorkflowGateSteps,
    blocked_kind,
    blocked_kind_counts,
    describe_engine,
    resolve_gate_steps,
    serve_command,
    serve_log_path,
    spawn_serve,
)
from .models import AUTONOMY_LEVELS, DecisionGate, EngineCommand, Event, Project, Run, Sprint, SprintStatus, Task
from .orchestrator import ForemanOrchestrator, OrchestratorError
from .scaffold import generate_project_id
from .settings import ProjectSettings, SettingsError
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
# Each tick now costs one PRAGMA data_version unless the DB actually changed, so
# we can poll more responsively without hammering the full sprint-events query.
STREAM_POLL_INTERVAL_SECONDS = 0.25

#: Recorded as the requester on commands the dashboard queues when the caller
#: did not name themselves. A shared token is not identity yet (MANUAL §17), so
#: the surface is the best attribution available.
DASHBOARD_REQUESTER = "dashboard"

#: How many engine commands the status payload carries.
ENGINE_COMMAND_LIMIT = 10


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


def _serialize_completion_evidence(evidence: "Any") -> dict[str, Any] | None:
    """Serialize a ``CompletionEvidence`` for the task detail payload.

    Returns ``None`` when the task has no evidence yet (the common case before a
    decision role runs).
    """
    if evidence is None:
        return None
    return {
        "verdict": evidence.verdict,
        "verdict_reasons": list(evidence.verdict_reasons),
        "proof_status": evidence.proof_status,
        "judged_by": evidence.judged_by,
        "score": evidence.score,
        "score_breakdown": evidence.score_breakdown,
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


def _serialize_engine_command(command: EngineCommand) -> dict[str, Any]:
    """Serialize one engine command row for the API."""

    return {
        "id": command.id,
        "command": command.command,
        "status": command.status,
        "task_id": command.task_id,
        "requested_by": command.requested_by,
        "requested_at": command.requested_at,
        "acknowledged_at": command.acknowledged_at,
        "completed_at": command.completed_at,
        "result_detail": command.result_detail,
    }


def _serialize_engine_state(engine: EngineStateView) -> dict[str, Any]:
    """Serialize the engine view shared by the status route and project payloads."""

    task = engine.current_task
    return {
        "resident": engine.resident,
        "paused": engine.paused,
        "state": engine.state,
        "holder_id": engine.holder_id,
        "heartbeat_age_seconds": engine.heartbeat_age_seconds,
        "heartbeat_at": engine.lock.heartbeat_at if engine.lock else None,
        "lease_expires_at": engine.lock.expires_at if engine.lock else None,
        "lease_expired": engine.lease_expired,
        "current_task": (
            {
                "id": task.id,
                "task_key": task.task_key,
                "title": task.title,
                "status": task.status,
                "workflow_current_step": task.workflow_current_step,
            }
            if task is not None
            else None
        ),
    }


def _validate_repo_path(repo_path: str) -> None:
    """Refuse project paths that are not existing git repositories.

    The manager chat and the engine run agents inside ``repo_path``, so it
    must never be an arbitrary directory on the host. When
    ``FOREMAN_DASHBOARD_REPO_ROOTS`` is set (``os.pathsep``-separated), the
    path must also sit under one of those roots.
    """

    repo_dir = Path(repo_path).expanduser()
    if not repo_dir.is_dir():
        raise DashboardValidationError(
            f"Repo path does not exist or is not a directory: {repo_path}"
        )
    if not (repo_dir / ".git").exists():
        raise DashboardValidationError(
            f"Repo path is not a git repository (no .git found): {repo_path}"
        )
    roots_setting = os.environ.get("FOREMAN_DASHBOARD_REPO_ROOTS", "").strip()
    if roots_setting:
        resolved = repo_dir.resolve()
        roots = [Path(root).expanduser().resolve() for root in roots_setting.split(os.pathsep) if root]
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise DashboardValidationError(
                f"Repo path {repo_path} is outside the allowed repository roots."
            )


class DashboardService:
    """Store-backed dashboard service used by FastAPI transport and UI clients."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        now_factory: Callable[[], datetime] | None = None,
        serve_spawner: ServeSpawner | None = None,
    ) -> None:
        self.store = store
        self._now = now_factory or (lambda: datetime.now(timezone.utc))
        # Injected so a test — and, later, a deployment that starts engines
        # somewhere other than this host — can replace the fork without
        # replacing the decision about when to fork.
        self._spawn_serve: ServeSpawner = serve_spawner or spawn_serve

    def list_projects(self) -> dict[str, Any]:
        """Return the project summary collection used by the dashboard landing screen."""

        result = []
        # Resolving a workflow reads every role and workflow TOML, so the
        # landing page resolves each distinct workflow once rather than once
        # per project.
        gates_by_workflow: dict[str, WorkflowGateSteps] = {}
        for project in self.store.list_projects():
            active_sprint = self.store.get_active_sprint(project.id)
            engine = describe_engine(self.store, project.id, now=self._now())
            if project.workflow_id not in gates_by_workflow:
                gates_by_workflow[project.workflow_id] = resolve_gate_steps(
                    project.workflow_id
                )
            result.append(
                {
                    "id": project.id,
                    "name": project.name,
                    "workflow_id": project.workflow_id,
                    "status": self.get_project_status(project.id),
                    "agent_running": engine.resident,
                    "engine": _serialize_engine_state(engine),
                    **self._blocked_kind_counts(
                        project, gates_by_workflow[project.workflow_id]
                    ),
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
        engine = describe_engine(self.store, project_id, now=self._now())
        return {
            "id": project.id,
            "name": project.name,
            "workflow_id": project.workflow_id,
            "default_branch": project.default_branch,
            "repo_path": project.repo_path,
            "spec_path": project.spec_path,
            "methodology": project.methodology,
            "autonomy_level": project.autonomy_level,
            "agent_running": engine.resident,
            "engine": _serialize_engine_state(engine),
            "task_counts": self.store.task_counts(project_id=project.id),
            **self._blocked_kind_counts(project),
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
            merged = dict(project.settings)
            merged.update(settings_updates)
            try:
                ProjectSettings.from_raw(merged)
            except SettingsError as exc:
                raise DashboardValidationError(f"Invalid settings: {exc}") from exc
            project.settings = merged

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
        _validate_repo_path(repo_path)
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
        requested_by: str | None = None,
    ) -> dict[str, Any]:
        """Ask the project's engine to start working.

        When an engine is resident the whole of "start" is a ``resume``
        command: the engine may be paused, or merely idle, and either way it
        is the engine that decides what to run next. When none is resident
        there is nobody to send that command to, so a detached ``foreman
        serve`` is spawned first — the single-machine fallback — and the
        command is queued for it to pick up on its first pass.

        A ``task_id`` becomes a ``run_task`` command rather than a CLI flag,
        so the request survives whether or not an engine is up yet.

        If no sprint is currently active and a planned sprint exists, the first
        planned sprint (by queue order) is activated before the engine starts.
        """

        project = self.store.get_project(project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")

        if task_id is not None:
            task = self._require_task(task_id)
            if task.project_id != project_id:
                raise DashboardValidationError(
                    f"Task {task_id} belongs to project {task.project_id}, not {project_id}."
                )

        if task_id is None and self.store.get_active_sprint(project_id) is None:
            next_sprint = self.store.get_next_planned_sprint(project_id)
            if next_sprint is None:
                raise DashboardValidationError(
                    "No active or planned sprint. Add a sprint to the queue before running."
                )
            now = self._now().isoformat()
            next_sprint.status = "active"
            next_sprint.started_at = now
            self.store.save_sprint(next_sprint)

        who = self._requester(requested_by)
        commands: list[EngineCommand] = []
        if task_id is not None:
            commands.append(
                self.store.enqueue_engine_command(
                    project_id=project_id,
                    command="run_task",
                    requested_by=who,
                    task_id=task_id,
                )
            )
        resume = self.store.enqueue_engine_command(
            project_id=project_id,
            command="resume",
            requested_by=who,
        )
        commands.append(resume)

        # Read residency after queueing: a `resume` queued for an engine that
        # is starting right now is honoured by it, so the only case that needs
        # a spawn is "still nothing holding the lock".
        resident = self.store.get_engine_lock(project_id) is not None
        payload: dict[str, Any] = {
            "project_id": project_id,
            "started": True,
            "resident": resident,
            "spawned": False,
            "requested_by": who,
            "command": _serialize_engine_command(resume),
            "commands": [_serialize_engine_command(command) for command in commands],
        }
        if not resident:
            payload.update(self._spawn_local_engine(project))
        return payload

    def _spawn_local_engine(self, project: Project) -> dict[str, Any]:
        """Start a detached ``foreman serve`` for a project with no engine."""

        log_path = serve_log_path(project)
        command = serve_command(project.id, self.store.db_path)
        try:
            spawn = self._spawn_serve(command, log_path)
        except OSError as exc:
            raise DashboardActionError(
                f"Could not start a resident engine for {project.id}: {exc}"
            ) from exc
        return {
            "spawned": True,
            "pid": spawn.pid,
            "log_path": spawn.log_path,
            "serve_command": list(spawn.command),
        }

    def agent_status(self, project_id: str) -> dict[str, Any]:
        """Report the engine's residency, pause state, work, and recent orders."""

        project = self.store.get_project(project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")
        engine = describe_engine(
            self.store,
            project_id,
            command_limit=ENGINE_COMMAND_LIMIT,
            now=self._now(),
        )
        payload = _serialize_engine_state(engine)
        payload["project_id"] = project_id
        payload["commands"] = [
            _serialize_engine_command(command) for command in engine.commands
        ]
        return payload

    def list_engine_commands(
        self,
        project_id: str,
        *,
        limit: int = ENGINE_COMMAND_LIMIT,
        status: str | None = None,
    ) -> dict[str, Any]:
        """List the project's recent engine commands, newest first."""

        if self.store.get_project(project_id) is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")
        limit = max(1, min(int(limit), 200))
        commands = self.store.list_engine_commands(
            project_id, status=status, limit=limit
        )
        return {
            "project_id": project_id,
            "commands": [_serialize_engine_command(command) for command in commands],
        }

    def list_project_sprints(self, project_id: str) -> dict[str, Any]:
        """Return sprint summaries for one project."""

        result = []
        for sprint in self.store.list_sprints(project_id):
            task_counts = self.store.task_counts(sprint_id=sprint.id)
            entry: dict[str, Any] = {
                "id": sprint.id,
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

        from .models import TASK_COMPLEXITIES, TASK_TYPES

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
            acceptance_criteria = task_data.get("acceptance_criteria") or None
            if acceptance_criteria:
                acceptance_criteria = str(acceptance_criteria).strip() or None
            description = task_data.get("description") or None
            if description:
                description = str(description).strip() or None
            complexity = task_data.get("complexity") or None
            if complexity is not None and complexity not in TASK_COMPLEXITIES:
                complexity = None
            task = Task(
                id=task_id,
                sprint_id=sprint_id,
                project_id=project_id,
                title=task_title,
                task_type=task_type,
                acceptance_criteria=acceptance_criteria,
                description=description,
                complexity=complexity,
                order_index=i,
                created_by="human",
                created_at=now,
            )
            self.store.save_task(task)
            created_tasks.append({"id": task.id, "task_key": task.task_key, "title": task.title, "task_type": task.task_type})

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
        result = []
        for task in self.store.list_tasks(sprint_id=sprint_id):
            metrics = task_totals.get(task.id, {})
            result.append(
                {
                    "id": task.id,
                    "task_key": task.task_key,
                    "title": task.title,
                    "status": task.status,
                    "task_type": task.task_type,
                    "priority": task.priority,
                    "branch_name": task.branch_name,
                    "assigned_role": task.assigned_role,
                    "blocked_reason": task.blocked_reason,
                    "acceptance_criteria": task.acceptance_criteria,
                    "workflow_current_step": task.workflow_current_step,
                    "awaiting_human_gate": self._at_human_gate(task, gates),
                    "blocked_kind": blocked_kind(task, gates),
                    "complexity": task.complexity,
                    "executor_overrides": task.executor_overrides,
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

        project = self.store.get_project(task.project_id)
        gates = self._gate_steps(project)

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
            "task_key": task.task_key,
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
            "complexity": task.complexity,
            "executor_overrides": task.executor_overrides or {},
            "awaiting_human_gate": self._at_human_gate(task, gates),
            "blocked_kind": blocked_kind(task, gates),
            "completion_evidence": _serialize_completion_evidence(task.completion_evidence),
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

        from .models import TASK_COMPLEXITIES, TASK_TYPES

        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise DashboardNotFoundError(f"Sprint not found: {sprint_id}")
        if not title.strip():
            raise DashboardValidationError("Task title is required.")

        if task_type not in TASK_TYPES:
            raise DashboardValidationError(
                f"Unsupported task type: {task_type}. "
                f"Expected one of: {', '.join(TASK_TYPES)}."
            )

        if complexity is not None and complexity not in TASK_COMPLEXITIES:
            raise DashboardValidationError(
                f"Unsupported complexity: {complexity}. "
                f"Expected one of: {', '.join(TASK_COMPLEXITIES)}."
            )

        depends_on_ids: list[str] = []
        for dep_id in depends_on or []:
            dep_id = str(dep_id).strip()
            if not dep_id:
                continue
            dep_task = self.store.get_task(dep_id)
            if dep_task is None or dep_task.project_id != sprint.project_id:
                raise DashboardValidationError(
                    f"Dependency task not found in this project: {dep_id}"
                )
            if dep_id not in depends_on_ids:
                depends_on_ids.append(dep_id)

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
            description=description.strip() if description and description.strip() else None,
            complexity=complexity,
            depends_on_task_ids=depends_on_ids,
            order_index=max((t.order_index for t in existing_tasks), default=-1) + 1,
            created_by="human",
            created_at=now,
        )
        task = self.store.save_task(task)
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

        from .models import TASK_TYPES, validate_executor_overrides

        task = self._require_task(task_id)
        allowed_fields = {
            "title",
            "task_type",
            "acceptance_criteria",
            "description",
            "priority",
            "executor_overrides",
        }
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
        if "executor_overrides" in updates:
            try:
                normalized = validate_executor_overrides(
                    updates["executor_overrides"],
                    valid_steps=self._project_workflow_step_ids(task.project_id),
                )
            except ValueError as exc:
                raise DashboardValidationError(str(exc)) from exc
            if normalized != (task.executor_overrides or {}):
                changed["executor_overrides"] = normalized
            task.executor_overrides = normalized

        self.store.save_task(task)

        if changed and task.status in {"in_progress", "blocked"}:
            now = self._now()
            now_text = now.isoformat()
            run_id = self._ensure_event_run(task, step="edit", outcome="edit", now=now)
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

    def stop_agent(self, project_id: str, *, requested_by: str | None = None) -> dict[str, Any]:
        """Ask the project's engine to pause, and return once the order is queued.

        Pausing is about the engine, not about the work: the engine terminates
        the running agent step and leaves its task resumable at the persisted
        step. Nothing here touches task status — a dashboard that blocked every
        in-progress task on Pause was inventing a dead letter the engine never
        declared.
        """

        if self.store.get_project(project_id) is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")

        who = self._requester(requested_by)
        command = self.store.enqueue_engine_command(
            project_id=project_id,
            command="pause",
            requested_by=who,
        )
        return {
            "project_id": project_id,
            "resident": self.store.get_engine_lock(project_id) is not None,
            "requested_by": who,
            "command": _serialize_engine_command(command),
        }

    def stop_task(self, task_id: str, *, requested_by: str | None = None) -> dict[str, Any]:
        """Ask the engine to stop one running task.

        The engine owns the transition: it terminates the agent step it is
        running and blocks the task with a reason naming the requester. A task
        the engine is not running is rejected on the command row rather than
        being blocked here behind the engine's back.
        """

        task = self._require_task(task_id)
        if task.status != "in_progress":
            raise DashboardValidationError(
                f"Cannot stop a task with status '{task.status}'; only in_progress tasks can be stopped."
            )

        who = self._requester(requested_by)
        command = self.store.enqueue_engine_command(
            project_id=task.project_id,
            command="stop_task",
            requested_by=who,
            task_id=task.id,
        )
        return {
            "task_id": task.id,
            "project_id": task.project_id,
            "status": task.status,
            "resident": self.store.get_engine_lock(task.project_id) is not None,
            "requested_by": who,
            "command": _serialize_engine_command(command),
        }

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
        running = self.store.list_runs(task_id=task.id, status="running")
        if running and self.store.get_engine_lock(task.project_id) is not None:
            raise DashboardValidationError(
                f"Task {task.id} has a running agent step ({running[0].id}); stop the "
                "task first, then cancel it."
            )
        task.status = "cancelled"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.completed_at = self._now().isoformat()
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

        now = self._now()
        run_id = self._ensure_event_run(task, step="message", outcome="message", now=now)
        event = Event(
            id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-{task_id[:8]}",
            run_id=run_id,
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

    def _project_workflow_step_ids(self, project_id: str) -> set[str] | None:
        """Return the workflow step ids for a project, or ``None`` if unresolved."""

        from .roles import RoleLoadError, load_roles
        from .workflows import WorkflowLoadError, load_workflows

        project = self.store.get_project(project_id)
        if project is None:
            return None
        try:
            roles = load_roles()
            workflows = load_workflows(
                available_role_ids=set(roles),
                role_outcomes={rid: role.completion.outcomes for rid, role in roles.items()},
            )
        except (RoleLoadError, WorkflowLoadError):
            return None
        workflow = workflows.get(project.workflow_id)
        if workflow is None:
            return None
        return {step.id for step in workflow.steps}

    @staticmethod
    def _at_human_gate(task: Task, gates: WorkflowGateSteps) -> bool:
        """True when a blocked task is waiting for Approve/Deny rather than a fix."""

        return blocked_kind(task, gates) == "gate"

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

    def _requester(self, requested_by: str | None) -> str:
        """Name recorded on a queued command; never blank."""

        value = (requested_by or "").strip()
        return value or DASHBOARD_REQUESTER

    def _gate_steps(self, project: Project | None) -> WorkflowGateSteps:
        """Resolve the human-gate steps of a project's workflow."""

        return resolve_gate_steps(project.workflow_id if project else None)

    def _blocked_kind_counts(
        self, project: Project, gates: WorkflowGateSteps | None = None
    ) -> dict[str, int]:
        """Dead-letter counts for a project summary, keyed for the API payload."""

        counts = blocked_kind_counts(
            self.store.list_tasks(project_id=project.id, status="blocked"),
            gates if gates is not None else self._gate_steps(project),
        )
        return {
            "blocked_gate": counts["gate"],
            "blocked_engine": counts["engine"],
        }

    def _ensure_event_run(
        self,
        task: Task,
        *,
        step: str,
        outcome: str,
        now: datetime | None = None,
    ) -> str:
        """Return a real run id for dashboard-authored task events."""

        runs = self.store.list_runs(task_id=task.id)
        if runs:
            return runs[-1].id

        timestamp = now or self._now()
        timestamp_text = timestamp.isoformat()
        synthetic_run = Run(
            id=f"run-{step}-{timestamp.strftime('%Y%m%d%H%M%S%f')}-{task.id[:8]}",
            task_id=task.id,
            project_id=task.project_id,
            role_id="human",
            workflow_step=step,
            agent_backend="dashboard",
            status="completed",
            outcome=outcome,
            started_at=timestamp_text,
            completed_at=timestamp_text,
            created_at=timestamp_text,
        )
        self.store.save_run(synthetic_run)
        return synthetic_run.id

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
