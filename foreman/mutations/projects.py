"""A project's record: registering it, and changing its fields and settings.

``foreman init`` and the dashboard's New project both register a project
here, and ``foreman config`` and the dashboard's settings both change one
here, so a setting is checked the same way whichever surface sets it.

Settings that decide what runs on the host (ADR-0017) are changed only where
the caller says the person is at a terminal (``host_level=True``). A surface
reached over a network refuses them, and the refusal names them
(``HostLevelSettingError``) so the surface can say where to change them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..definitions.layers import project_definitions
from ..definitions.roles import RoleLoadError
from ..definitions.workflows import WorkflowLoadError
from ..domain.models import AUTONOMY_LEVELS, Project
from ..domain.settings import (
    HOST_LEVEL_SETTINGS,
    ProjectSettings,
    SettingsError,
    changed_host_level_settings,
)
from ..repo.scaffold import generate_project_id, new_project_settings
from .base import MutationBase, MutationError

#: A project's own fields a person may change, besides its settings.
PROJECT_EDIT_FIELDS: tuple[str, ...] = ("workflow_id", "default_branch", "spec_path", "autonomy_level")


class SettingError(MutationError):
    """A setting's value is not valid.

    ``field`` names the setting when the refusal is about one; ``detail`` is
    the reason without the "Invalid settings" preface, for a surface that
    words it itself.
    """

    def __init__(self, message: str, *, field: str | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.field = field
        self.detail = detail if detail is not None else message


class HostLevelSettingError(MutationError):
    """Host-level settings were sent from where they cannot be changed (ADR-0017)."""

    def __init__(self, project_id: str, settings: Sequence[str]) -> None:
        super().__init__(f"{', '.join(settings)} can be changed only at a terminal.")
        self.project_id = project_id
        self.settings = tuple(settings)


def allocate_project_id(store: Any, name: str, repo_path: str) -> str:
    """A readable id for a new project, numbered when already taken."""

    base_id = generate_project_id(name, repo_path)
    candidate = base_id
    suffix = 2
    while store.get_project(candidate) is not None:
        candidate = f"{base_id}-{suffix}"
        suffix += 1
    return candidate


class ProjectMutations(MutationBase):
    """Registering a project, and changing its fields and settings."""

    def register_project(
        self,
        *,
        name: str,
        repo_path: str,
        workflow_id: str,
        settings: Mapping[str, Any] | None = None,
        spec_path: str | None = None,
        methodology: str | None = None,
        default_branch: str | None = None,
    ) -> Project:
        """Register a new project; its settings default to a new project's (ADR-0017)."""

        clean_name = (name or "").strip()
        if not clean_name:
            raise MutationError("Project name cannot be empty.")
        clean_path = (repo_path or "").strip()
        if not clean_path:
            raise MutationError("Repo path cannot be empty.")
        clean_workflow = (workflow_id or "").strip()
        if not clean_workflow:
            raise MutationError("Workflow ID cannot be empty.")
        optional = {
            key: value
            for key, value in (
                ("spec_path", spec_path),
                ("methodology", methodology),
                ("default_branch", default_branch),
            )
            if value is not None
        }
        now = self._now().isoformat()
        project = Project(
            id=allocate_project_id(self.store, clean_name, clean_path),
            name=clean_name,
            repo_path=clean_path,
            workflow_id=clean_workflow,
            settings=dict(settings) if settings is not None else new_project_settings(),
            created_at=now,
            updated_at=now,
            **optional,
        )
        self.store.save_project(project)
        return project

    def reregister_project(
        self,
        project: Project,
        *,
        name: str,
        spec_path: str,
        methodology: str,
        workflow_id: str,
        default_branch: str,
        settings: Mapping[str, Any],
    ) -> Project:
        """Register an existing project again (``foreman init`` on its folder)."""

        project.name = name
        project.spec_path = spec_path
        project.methodology = methodology
        project.workflow_id = workflow_id
        project.default_branch = default_branch
        project.settings = dict(settings)
        project.updated_at = self._now().isoformat()
        self.store.save_project(project)
        return project

    def change_project(
        self,
        project: Project,
        *,
        fields: Mapping[str, Any] | None = None,
        settings: Mapping[str, Any] | None = None,
        host_level: bool,
    ) -> Project:
        """Change a project's fields and settings, all checked before any is written.

        ``fields`` names ``PROJECT_EDIT_FIELDS``. ``settings`` are merged over
        the project's own. ``host_level`` is true only for a person at a
        terminal; otherwise a change to a host-level setting is refused.
        """

        fields = dict(fields or {})
        unknown = sorted(set(fields) - set(PROJECT_EDIT_FIELDS))
        if unknown:
            raise MutationError(f"Unknown setting: {unknown[0]}")

        merged = dict(project.settings)
        if settings is not None:
            if not isinstance(settings, Mapping):
                raise SettingError("Settings must be a JSON object.")
            if not host_level:
                blocked = changed_host_level_settings(project.settings, settings)
                if blocked:
                    raise HostLevelSettingError(project.id, blocked)
            merged.update(
                {
                    key: value
                    for key, value in settings.items()
                    if host_level or key not in HOST_LEVEL_SETTINGS
                }
            )
            # Each key is checked alone first, so the refusal names the setting
            # it is about and a client can show it beside that field.
            for key, value in settings.items():
                try:
                    ProjectSettings.from_raw({key: value})
                except SettingsError as exc:
                    raise SettingError(str(exc), field=key) from exc
            try:
                ProjectSettings.from_raw(merged)
            except SettingsError as exc:
                raise SettingError(f"Invalid settings: {exc}", detail=str(exc)) from exc

        if "workflow_id" in fields:
            workflow_id = str(fields["workflow_id"])
            try:
                workflows = project_definitions(self.store, project.id).workflows
            except (RoleLoadError, WorkflowLoadError) as exc:
                raise MutationError(f"The workflow could not be loaded: {exc}") from exc
            if workflow_id not in workflows:
                raise SettingError(f"There is no workflow {workflow_id!r}.", field="workflow_id")
        # The workflow's routes may only name the labels and path groups this
        # project names: checked when either changes, not only the workflow
        # (sprint 69 review: removing a label a route named stopped the
        # project's engine).
        route_fields = {"labels", "path_groups"} & set(settings or {})
        if "workflow_id" in fields or route_fields:
            workflow_id = str(fields.get("workflow_id") or project.workflow_id or "")
            try:
                workflows = project_definitions(self.store, project.id).workflows
            except (RoleLoadError, WorkflowLoadError) as exc:
                raise MutationError(f"The workflow could not be loaded: {exc}") from exc
            chosen = workflows.get(workflow_id)
            if chosen is not None:
                named = ProjectSettings.from_raw(merged)
                unnamed = chosen.route_project_errors(
                    labels=named.labels, path_groups=named.path_groups
                )
                if unnamed:
                    field = "workflow_id" if "workflow_id" in fields else sorted(route_fields)[0]
                    raise SettingError(
                        f"Workflow {workflow_id!r} cannot be used by this project: {' '.join(unnamed)}",
                        field=field,
                    )
        if "autonomy_level" in fields:
            value = str(fields["autonomy_level"])
            if value not in AUTONOMY_LEVELS:
                raise SettingError(
                    f"Invalid autonomy_level: '{value}'. "
                    f"Expected one of: {', '.join(AUTONOMY_LEVELS)}."
                )

        project.settings = merged
        for key in PROJECT_EDIT_FIELDS:
            if key in fields:
                setattr(project, key, str(fields[key]))
        project.updated_at = self._now().isoformat()
        self.store.save_project(project)
        return project
