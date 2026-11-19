"""Projects: the list, one project, its settings and policy, and creating one.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..definitions.gate_steps import (
    WorkflowGateSteps,
    resolve_gate_steps,
)
from ..domain.models import (
    Project,
)
from ..domain.policy import PolicyMatrix, describe_resolution
from ..domain.settings import (
    HOST_LEVEL_SETTINGS,
    SettingsError,
    settings_of,
)
from ..engine.control import (
    describe_engine,
)
from ..mutations import MutationError
from ..mutations.projects import HostLevelSettingError, SettingError
from ..store import ForemanStore
from .base import Service
from .definitions import DefinitionService
from .errors import (
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
)
from .views import serialize_engine_state


def _validate_repo_path(repo_path: str) -> None:
    """Refuse project paths that are not existing git repositories.

    The manager chat and the engine run agents inside ``repo_path``, so it
    must never be an arbitrary directory on the host. When
    ``FOREMAN_DASHBOARD_REPO_ROOTS`` is set (``os.pathsep``-separated), the
    path must also sit under one of those roots.
    """

    repo_dir = Path(repo_path).expanduser()
    if not repo_dir.is_dir():
        raise InvalidRequestError(
            f"Repo path does not exist or is not a directory: {repo_path}"
        )
    if not (repo_dir / ".git").exists():
        raise InvalidRequestError(
            f"Repo path is not a git repository (no .git found): {repo_path}"
        )
    roots_setting = os.environ.get("FOREMAN_DASHBOARD_REPO_ROOTS", "").strip()
    if roots_setting:
        resolved = repo_dir.resolve()
        roots = [Path(root).expanduser().resolve() for root in roots_setting.split(os.pathsep) if root]
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise InvalidRequestError(
                f"Repo path {repo_path} is outside the allowed repository roots."
            )


class ProjectService(Service):
    """Projects: listing, one project, its settings and policy, creating one."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        now_factory: Callable[[], datetime] | None = None,
        definitions: DefinitionService,
    ) -> None:
        super().__init__(store, now_factory=now_factory)
        self.definitions = definitions

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
            if project.id not in gates_by_workflow:
                gates_by_workflow[project.id] = resolve_gate_steps(self.store, project)
            result.append(
                {
                    "id": project.id,
                    "name": project.name,
                    "workflow_id": project.workflow_id,
                    "status": self.get_project_status(project.id),
                    "agent_running": engine.resident,
                    "engine": serialize_engine_state(engine),
                    **self._blocked_kind_counts(
                        project, gates_by_workflow[project.id]
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
            raise NotFoundError(f"Project not found: {project_id}")
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
            "engine": serialize_engine_state(engine),
            "task_counts": self.store.task_counts(project_id=project.id),
            **self._blocked_kind_counts(project),
            "totals": self.store.run_totals(project_id=project_id),
        }

    def get_project_settings(self, project_id: str) -> dict[str, Any]:
        """Return settings for one project."""

        project = self.store.get_project(project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {project_id}")
        return {
            "project_id": project.id,
            "workflow_id": project.workflow_id,
            "default_branch": project.default_branch,
            "spec_path": project.spec_path or "",
            "autonomy_level": project.autonomy_level,
            "settings": dict(project.settings),
            # Every setting as it applies, defaults filled in: what the engine
            # reads, so a screen need not repeat the defaults.
            "effective": self._effective_settings(project),
            # Shown read-only in the dashboard; see HOST_LEVEL_SETTINGS.
            "host_level_settings": sorted(HOST_LEVEL_SETTINGS),
        }

    @staticmethod
    def _effective_settings(project: Project) -> dict[str, Any]:
        """The project's settings with defaults applied, as plain JSON values."""

        try:
            settings = settings_of(project)
        except SettingsError as exc:
            raise InvalidRequestError(
                f"This project's stored settings are invalid: {exc}"
            ) from exc
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in asdict(settings).items()
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
            raise NotFoundError(f"Project not found: {project_id}")
        fields = {key: value for key, value in updates.items() if key != "settings"}
        try:
            self._mutations().change_project(
                project, fields=fields, settings=updates.get("settings"), host_level=False
            )
        except HostLevelSettingError as exc:
            raise ForbiddenError(
                f"{', '.join(exc.settings)} cannot be changed through the dashboard: "
                "these settings decide what runs on the host. Change them at a "
                f"terminal with `foreman config {project.id} --set <key>=<value>`."
            ) from exc
        except SettingError as exc:
            raise InvalidRequestError(str(exc), field=exc.field) from exc
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self.get_project_settings(project_id)

    def create_project(
        self,
        *,
        name: str,
        repo_path: str,
        workflow_id: str = "development",
    ) -> dict[str, Any]:
        """Register a new project record in the dashboard."""

        if repo_path.strip():
            _validate_repo_path(repo_path.strip())
        try:
            project = self._mutations().register_project(
                name=name, repo_path=repo_path, workflow_id=workflow_id or "development"
            )
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return {
            "id": project.id,
            "name": project.name,
            "repo_path": project.repo_path,
            "workflow_id": project.workflow_id,
            "status": "idle",
        }

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
                raise InvalidRequestError(
                    "Task does not belong to this project."
                )
            payload["task_id"] = task.id
            payload["task_type"] = task.task_type
            payload["overrides"] = task.executor_overrides or {}
            payload["resolution"] = describe_resolution(matrix.resolve_task(task))
        return payload

    def get_project_status(self, project_id: str) -> str:
        """Derive one project status from its task states."""

        tasks = self.store.list_tasks(project_id=project_id)
        if any(task.status == "in_progress" for task in tasks):
            return "running"
        if any(task.status == "blocked" for task in tasks):
            return "blocked"
        return "idle"
