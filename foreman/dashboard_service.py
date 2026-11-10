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
from urllib.parse import urlsplit

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
from .api_tokens import INTAKE_SCOPE
from .models import (
    AUTONOMY_LEVELS,
    ApiToken,
    DecisionGate,
    EngineCommand,
    Event,
    Project,
    Run,
    Sprint,
    SprintStatus,
    Task,
)
from .orchestrator import ForemanOrchestrator, OrchestratorError
from .policy import PolicyMatrix, describe_resolution
from .scaffold import generate_project_id
from .settings import (
    HOST_LEVEL_SETTINGS,
    ProjectSettings,
    SettingsError,
    changed_host_level_settings,
)
from .store import ForemanStore
from .worktrees import (
    WorktreeEntry,
    WorktreeError,
    WorktreeManager,
    max_live_worktrees,
    prune_project_worktrees,
    worktree_root,
)

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

#: Suffix of a project's intake queue sprint id, and its title. The queue is a
#: real sprint (ADR-0013): sprints stay the unit of grouping, and a continuous
#: queue is simply a sprint that never completes.
INTAKE_SPRINT_SUFFIX = "-intake"
INTAKE_SPRINT_TITLE = "Intake queue"
INTAKE_SPRINT_GOAL = (
    "Work handed to Foreman by other systems through the intake API. "
    "This sprint is a standing queue and is not expected to complete."
)


class DashboardServiceError(Exception):
    """Base error for dashboard service failures."""


class DashboardNotFoundError(DashboardServiceError):
    """Raised when one requested dashboard resource does not exist."""


class DashboardValidationError(DashboardServiceError):
    """Raised when one dashboard request payload is invalid."""


class DashboardActionError(DashboardServiceError):
    """Raised when one dashboard action cannot be completed."""


class DashboardAuthError(DashboardServiceError):
    """Raised when a request presents no usable credential (HTTP 401)."""


class DashboardPermissionError(DashboardServiceError):
    """Raised when a valid credential is not allowed to do this (HTTP 403)."""


_ALLOWED_ROLE_FIELDS: frozenset[str] = frozenset(
    {"backend", "model", "permission_mode", "timeout_minutes", "max_cost_usd"}
)
_HOST_LEVEL_ROLE_FIELDS: frozenset[str] = frozenset({"backend", "permission_mode"})


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


def _serialize_task_source(task: Task) -> dict[str, Any] | None:
    """Return where a task came from, or None when a person filed it.

    Absent rather than empty: the drawer renders a Source section only for work
    that arrived from another system, so tasks created in the UI stay clean.
    """

    if not any((task.source_system, task.source_ref, task.source_url, task.reporter)):
        return None
    return {
        "system": task.source_system,
        "external_ref": task.source_ref,
        "url": task.source_url,
        "reporter": task.reporter,
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
            # Shown read-only in the dashboard; see HOST_LEVEL_SETTINGS.
            "host_level_settings": sorted(HOST_LEVEL_SETTINGS),
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
            blocked = changed_host_level_settings(project.settings, settings_updates)
            if blocked:
                raise DashboardPermissionError(
                    f"{', '.join(blocked)} cannot be changed through the dashboard: "
                    "these settings decide what runs on the host. Change them at a "
                    f"terminal with `foreman config {project.id} --set <key>=<value>`."
                )
            merged = dict(project.settings)
            merged.update(
                {
                    key: value
                    for key, value in settings_updates.items()
                    if key not in HOST_LEVEL_SETTINGS
                }
            )
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
                    "source": _serialize_task_source(task),
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
            "worktree_path": task.worktree_path,
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
            "source": _serialize_task_source(task),
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

    def accept_task(self, task_id: str) -> dict[str, Any]:
        """Accept one task out of triage and into the runnable queue."""

        task = self._require_task(task_id)
        if task.status != "triage":
            raise DashboardValidationError(
                f"Cannot accept a task with status '{task.status}'; only tasks in "
                "triage can be accepted."
            )
        task.status = "todo"
        self.store.save_task(task)
        now = self._now()
        run_id = self._ensure_event_run(task, step="triage", outcome="accepted", now=now)
        self.store.save_event(
            Event(
                id=f"evt-triage-{now.strftime('%Y%m%d%H%M%S%f')}-{task.id[:8]}",
                run_id=run_id,
                task_id=task.id,
                project_id=task.project_id,
                event_type="human.task_accepted",
                role_id="human",
                timestamp=now.isoformat(),
                payload={"task_key": task.task_key, "from_status": "triage"},
            )
        )
        return self.get_task(task.id)

    def get_project_policy(
        self, project_id: str, *, task_id: str | None = None
    ) -> dict[str, Any]:
        """Return the project's policy matrix, optionally resolved for one task.

        Without ``task_id`` this is the project side alone: the defaults, where
        each came from, and the per-task-type rules. With one, ``resolution``
        carries the four decisions as they apply to that task, so a reader can
        see the effect of its overrides and its type's rule.
        """

        project = self._require_project(project_id)
        matrix = PolicyMatrix.for_project(project)
        payload: dict[str, Any] = {"project_id": project.id, **matrix.describe()}
        if task_id is not None:
            task = self._require_task(task_id)
            if task.project_id != project.id:
                raise DashboardValidationError(
                    "Task does not belong to this project."
                )
            payload["task_id"] = task.id
            payload["task_type"] = task.task_type
            payload["overrides"] = task.executor_overrides or {}
            payload["resolution"] = describe_resolution(matrix.resolve_task(task))
        return payload

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
        removed = self._discard_task_worktree(task)
        self.store.save_task(task)
        return {
            "status": "cancelled",
            "task_id": task_id,
            "removed_worktree": removed,
        }

    def delete_task(self, task_id: str) -> dict[str, Any]:
        """Delete one task, its history, and the worktree it was working in."""

        task = self._require_task(task_id)
        project_id = task.project_id
        self._discard_task_worktree(task)
        self.store.delete_task(task_id)
        return {"ok": "deleted", "task_id": task_id, "project_id": project_id}

    def _discard_task_worktree(self, task: Task) -> str | None:
        """Remove a finished task's worktree; return the path that went away.

        Best effort by design: the task row is the record that matters, and
        `foreman worktree prune` exists to sweep up anything left behind.
        """

        recorded = task.worktree_path
        if not recorded:
            return None
        project = self.store.get_project(task.project_id)
        if project is None:
            return None
        try:
            WorktreeManager(project).remove_path(Path(recorded))
        except (WorktreeError, OSError):
            return None
        task.worktree_path = None
        return recorded

    def list_worktrees(self, project_id: str) -> dict[str, Any]:
        """Return the Foreman-owned worktrees for one project.

        The project screen shows what the engine is holding on disk so an
        operator can see whether a prune would free anything before running it.
        """

        project = self._require_project(project_id)
        tasks_by_path = {
            task.worktree_path: task
            for task in self.store.list_tasks(project_id=project.id)
            if task.worktree_path
        }
        try:
            entries = WorktreeManager(project).list()
        except WorktreeError as exc:
            raise DashboardValidationError(str(exc)) from exc
        return {
            "project_id": project.id,
            "root": str(worktree_root(project)),
            "max_live_worktrees": max_live_worktrees(project),
            "worktrees": [
                self._serialize_worktree(entry, tasks_by_path.get(str(entry.path)))
                for entry in entries
            ],
        }

    def prune_worktrees(
        self,
        project_id: str,
        *,
        requested_by: str | None = None,
    ) -> dict[str, Any]:
        """Remove the worktrees of done, cancelled, and vanished tasks.

        The same policy as ``foreman worktree prune``: it never touches the
        integration tree or a live task's tree, so it is safe to offer as a
        one-click control.
        """

        project = self._require_project(project_id)
        try:
            removed, kept = prune_project_worktrees(self.store, project)
        except WorktreeError as exc:
            raise DashboardValidationError(str(exc)) from exc

        # Forget the paths that no longer exist so the task drawer stops
        # advertising a directory an operator cannot open.
        removed_paths = {str(entry.path) for entry in removed}
        for task in self.store.list_tasks(project_id=project.id):
            if task.worktree_path and task.worktree_path in removed_paths:
                task.worktree_path = None
                self.store.save_task(task)

        return {
            "ok": "pruned",
            "project_id": project.id,
            "root": str(worktree_root(project)),
            "requested_by": self._requester(requested_by),
            "removed": [self._serialize_worktree(entry, None) for entry in removed],
            "kept": [self._serialize_worktree(entry, None) for entry in kept],
        }

    @staticmethod
    def _serialize_worktree(
        entry: WorktreeEntry,
        task: Task | None,
    ) -> dict[str, Any]:
        return {
            "slug": entry.slug,
            "path": str(entry.path),
            "branch": entry.branch,
            "exists": entry.exists,
            "is_integration": entry.is_integration,
            "owned": entry.owned,
            "task_id": task.id if task is not None else None,
            "task_key": (task.task_key or task.id) if task is not None else None,
            "task_status": task.status if task is not None else None,
        }

    def _require_project(self, project_id: str) -> Project:
        """Return one project or raise the dashboard's not-found error."""

        project = self.store.get_project(project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {project_id}")
        return project

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

        # What an agent may do on the host is not a dashboard decision. A
        # client that sends back the value it read is not changing anything.
        blocked = sorted(
            key
            for key in _HOST_LEVEL_ROLE_FIELDS
            if key in updates and updates[key] != doc["agent"].get(key)
        )
        if blocked:
            raise DashboardPermissionError(
                f"{', '.join(blocked)} cannot be changed through the dashboard: "
                "these fields decide what an agent may do on the host. Edit "
                f"{Path(role.source_path).name} in the roles directory instead."
            )

        for key, value in updates.items():
            if key in ("backend", "model", "permission_mode"):
                doc["agent"][key] = value
            elif key == "timeout_minutes":
                doc["completion"]["timeout_minutes"] = int(value)
            elif key == "max_cost_usd":
                doc["completion"]["max_cost_usd"] = float(value)

        # Validate the new file before it replaces the old one, so a bad value
        # never leaves a role that fails to load.
        source_path = Path(role.source_path)
        candidate = source_path.with_name(f".{source_path.name}.tmp")
        try:
            with open(candidate, "w", encoding="utf-8") as fh:
                tomlkit.dump(doc, fh)
            try:
                load_role(candidate)
            except RoleLoadError as exc:
                raise DashboardValidationError(f"Invalid role update: {exc}") from exc
            os.replace(candidate, source_path)
        finally:
            candidate.unlink(missing_ok=True)

        return _serialize_role(load_role(source_path))

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
        role_id: str = "human",
        agent_backend: str = "dashboard",
    ) -> str:
        """Return a real run id for dashboard-authored task events.

        ``role_id`` and ``agent_backend`` name the author of the synthetic run,
        so an event filed by the intake API is distinguishable from one a
        person clicked.
        """

        runs = self.store.list_runs(task_id=task.id)
        if runs:
            return runs[-1].id

        timestamp = now or self._now()
        timestamp_text = timestamp.isoformat()
        synthetic_run = Run(
            id=f"run-{step}-{timestamp.strftime('%Y%m%d%H%M%S%f')}-{task.id[:8]}",
            task_id=task.id,
            project_id=task.project_id,
            role_id=role_id,
            workflow_step=step,
            agent_backend=agent_backend,
            status="completed",
            outcome=outcome,
            started_at=timestamp_text,
            completed_at=timestamp_text,
            created_at=timestamp_text,
        )
        self.store.save_run(synthetic_run)
        return synthetic_run.id

    # ── Intake ────────────────────────────────────────────────────────────────

    def authenticate_intake(self, project_id: str, secret: str | None) -> ApiToken:
        """Resolve the API token allowed to file work on this project.

        401 when no live token matches the secret, 403 when a live token
        belongs to another project or lacks the ``intake`` scope. The two are
        kept apart deliberately: a caller that gets 403 knows its credential is
        real and its configuration is wrong.
        """

        presented = (secret or "").strip()
        if not presented:
            raise DashboardAuthError(
                "Unauthorized: send an intake API token as `Authorization: Bearer <token>`."
            )
        token = self.store.find_api_token(presented)
        if token is None:
            raise DashboardAuthError("Unauthorized: unknown or revoked API token.")
        if token.project_id != project_id:
            raise DashboardPermissionError(
                "Forbidden: this API token belongs to a different project."
            )
        if not token.has_scope(INTAKE_SCOPE):
            raise DashboardPermissionError(
                f"Forbidden: this API token does not carry the `{INTAKE_SCOPE}` scope."
            )
        return token

    def intake_task(
        self,
        project_id: str,
        *,
        token: ApiToken,
        title: str,
        description: str | None = None,
        acceptance_criteria: str | None = None,
        task_type: str = "fix",
        priority: int = 0,
        complexity: str | None = None,
        source: dict[str, Any] | None = None,
        sprint_id: str | None = None,
    ) -> dict[str, Any]:
        """File one task handed to Foreman by another system.

        Returns the task serialized as ``GET /api/tasks/{id}`` serializes it,
        plus ``created``: False means the same ``(system, external_ref)`` was
        already filed and this call changed nothing. The transport turns that
        flag into 201 or 200.
        """

        from .models import TASK_COMPLEXITIES, TASK_TYPES

        project = self._require_project(project_id)

        clean_title = (title or "").strip()
        if not clean_title:
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
        try:
            priority_value = int(priority or 0)
        except (TypeError, ValueError):
            raise DashboardValidationError("'priority' must be an integer.") from None

        source_fields = self._normalize_intake_source(source)

        # Idempotency: the same incident posted twice is one task. Only a
        # caller that names both its system and its own reference for the work
        # gets this guarantee -- without a key there is nothing to match on.
        if source_fields["system"] and source_fields["external_ref"]:
            existing = self.store.find_task_by_source(
                project_id=project_id,
                source_system=source_fields["system"],
                source_ref=source_fields["external_ref"],
            )
            if existing is not None:
                payload = self.get_task(existing.id)
                payload["created"] = False
                return payload

        if sprint_id:
            sprint = self.store.get_sprint(sprint_id)
            if sprint is None:
                raise DashboardNotFoundError(f"Sprint not found: {sprint_id}")
            if sprint.project_id != project_id:
                raise DashboardValidationError(
                    "Sprint does not belong to this project."
                )
        else:
            sprint = self._ensure_intake_sprint(project)

        task_id = f"task-{_stable_slug(clean_title)}"
        suffix = 2
        while self.store.get_task(task_id) is not None:
            task_id = f"task-{_stable_slug(clean_title)}-{suffix}"
            suffix += 1

        existing_tasks = self.store.list_tasks(sprint_id=sprint.id)
        now = self._now()
        # The triage policy decides whether filed work is runnable on arrival.
        # `human` parks it in `triage`, where the engine will not pick it up,
        # until a person accepts it; `auto` sends it straight to the queue.
        triage_decision = PolicyMatrix.for_project(project).resolve(
            "triage", task_type=task_type
        )
        status = "triage" if triage_decision.value == "human" else "todo"
        task = Task(
            id=task_id,
            sprint_id=sprint.id,
            project_id=project_id,
            title=clean_title,
            status=status,  # type: ignore[arg-type]
            task_type=task_type,  # type: ignore[arg-type]
            description=(description or "").strip() or None,
            acceptance_criteria=(acceptance_criteria or "").strip() or None,
            complexity=complexity,
            priority=priority_value,
            order_index=max((t.order_index for t in existing_tasks), default=-1) + 1,
            # The audit trail names the token, never the secret.
            created_by=f"api:{token.name}",
            source_system=source_fields["system"],
            source_ref=source_fields["external_ref"],
            source_url=source_fields["url"],
            reporter=source_fields["reporter"],
            created_at=now.isoformat(),
        )
        task = self.store.save_task(task)

        run_id = self._ensure_event_run(
            task,
            step="intake",
            outcome="created",
            now=now,
            role_id="api",
            agent_backend="api",
        )
        self.store.save_event(
            Event(
                id=f"evt-intake-{now.strftime('%Y%m%d%H%M%S%f')}-{task.id[:8]}",
                run_id=run_id,
                task_id=task.id,
                project_id=project_id,
                event_type="intake.task_created",
                role_id="api",
                timestamp=now.isoformat(),
                payload={
                    "task_key": task.task_key,
                    "title": task.title,
                    "task_type": task.task_type,
                    "sprint_id": sprint.id,
                    "created_by": task.created_by,
                    "status": task.status,
                    "triage": triage_decision.as_dict(),
                    # The token's identity, never its secret.
                    "token_id": token.id,
                    "token_name": token.name,
                    "source": _serialize_task_source(task) or {},
                },
            )
        )

        if task.status == "triage":
            self._emit_task_attention(task, project, trigger="triage", run_id=run_id, now=now)

        payload = self.get_task(task.id)
        payload["created"] = True
        return payload

    def _emit_task_attention(
        self,
        task: Task,
        project: Project,
        *,
        trigger: str,
        run_id: str,
        now: datetime,
    ) -> None:
        """Raise one attention turn for a task the engine cannot progress."""

        notify = (
            PolicyMatrix.for_project(project)
            .resolve(
                "notification",
                task_type=task.task_type,
                overrides=task.executor_overrides,
            )
            .value
        )
        self.store.save_event(
            Event(
                id=f"evt-attention-{now.strftime('%Y%m%d%H%M%S%f')}-{task.id[:8]}",
                run_id=run_id,
                task_id=task.id,
                project_id=project.id,
                event_type="engine.attention_needed",
                role_id="api",
                timestamp=now.isoformat(),
                payload={"trigger": trigger, "task_id": task.id, "notify": notify},
            )
        )

    @staticmethod
    def _normalize_intake_source(source: dict[str, Any] | None) -> dict[str, str | None]:
        """Validate the caller's ``source`` object into task columns."""

        if source is None:
            source = {}
        if not isinstance(source, dict):
            raise DashboardValidationError("'source' must be an object.")
        unknown = set(source) - {"system", "external_ref", "url", "reporter"}
        if unknown:
            raise DashboardValidationError(
                "Unknown `source` fields: "
                f"{', '.join(sorted(unknown))}. "
                "Expected: system, external_ref, url, reporter."
            )
        normalized: dict[str, str | None] = {}
        for field_name in ("system", "external_ref", "url", "reporter"):
            value = source.get(field_name)
            if value is None:
                normalized[field_name] = None
                continue
            if not isinstance(value, str):
                raise DashboardValidationError(
                    f"'source.{field_name}' must be a string."
                )
            normalized[field_name] = value.strip() or None
        url = normalized["url"]
        if url is not None and urlsplit(url).scheme.lower() not in {"http", "https"}:
            # The dashboard renders this as a link.
            raise DashboardValidationError("'source.url' must be an http or https URL.")
        return normalized

    def _ensure_intake_sprint(self, project: Project) -> Sprint:
        """Return the project's intake queue, creating or reopening it.

        The queue is `<project>-intake`. It is created on first use and is
        `active` when the project has no active sprint, `planned` when one is
        already running -- the engine runs exactly one active sprint at a time,
        and intake must not silently displace the sprint a team is mid-way
        through. A queue left `planned` (or wrongly completed) is reactivated
        on the next intake once the project has no active sprint, so queued
        work does not sit forever behind a sprint that has since finished.
        """

        sprint_id = f"{project.id}{INTAKE_SPRINT_SUFFIX}"
        existing = self.store.get_sprint(sprint_id)
        active = self.store.get_active_sprint(project.id)
        now = self._now().isoformat()

        if existing is not None:
            if existing.status != "active" and active is None:
                existing.status = "active"
                existing.started_at = existing.started_at or now
                existing.completed_at = None
                self.store.save_sprint(existing)
            return existing

        sprints = self.store.list_sprints(project.id)
        sprint = Sprint(
            id=sprint_id,
            project_id=project.id,
            title=INTAKE_SPRINT_TITLE,
            goal=INTAKE_SPRINT_GOAL,
            status="active" if active is None else "planned",
            order_index=max((s.order_index for s in sprints), default=-1) + 1,
            created_at=now,
            started_at=now if active is None else None,
        )
        return self.store.save_sprint(sprint)

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
