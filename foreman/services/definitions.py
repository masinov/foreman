"""Roles and workflows as a person reads and edits them (ADR-0024).
"""

from __future__ import annotations

from typing import Any

from ..definitions.layers import (
    DefinitionError,
    project_definitions,
    workspace_definitions,
)
from ..definitions.roles import RoleLoadError
from ..definitions.workflows import WorkflowLoadError
from ..domain.settings import (
    settings_of,
)
from .base import Service
from .definition_forms import (
    describe_project_definitions,
    reset_from_dashboard,
    save_from_dashboard,
)
from .errors import (
    ActionFailedError,
    InvalidRequestError,
    NotFoundError,
)
from .workflow_reads import describe_workflow


def _serialize_role(role: "Any") -> dict[str, Any]:
    """Serialize one RoleDefinition to a JSON-friendly dict."""

    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "backend": role.agent.backend,
        "model": role.agent.model,
        "model_ladder": list(role.agent.model_ladder),
        "escalate_after": role.agent.escalate_after,
        "permission_mode": role.agent.permission_mode,
        "session_persistence": role.agent.session_persistence,
        "timeout_minutes": role.completion.timeout_minutes,
        "max_cost_usd": role.completion.max_cost_usd,
        "source_path": str(role.source_path),
    }


class DefinitionService(Service):
    """Roles and workflows: the catalogue, a project's own, saving and resetting them."""

    def workflow_catalogue(
        self, project_id: str | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Every role and workflow definition, as ``(roles, workflows)``.

        With a project, the ones that project runs with: the shipped
        definitions with the project's own over them (ADR-0024).
        """

        try:
            definitions = project_definitions(self.store, project_id)
        except (RoleLoadError, WorkflowLoadError) as exc:
            raise InvalidRequestError(f"The workflow could not be loaded: {exc}") from exc
        return definitions.roles, definitions.workflows

    def get_project_workflow(self, project_id: str) -> dict[str, Any]:
        """The project's workflow: steps, transitions, roles and what finishing requires."""

        project = self._require_project(project_id)
        roles, workflows = self.workflow_catalogue(project_id)
        workflow = workflows.get(project.workflow_id)
        if workflow is None:
            raise NotFoundError(f"Workflow not found: {project.workflow_id}")
        return {
            **describe_workflow(workflow, roles),
            # Whether the engine holds a merge to these requirements.
            "requirements_enforced": settings_of(project).completion_guard_enabled,
        }

    def list_workflows(self) -> dict[str, Any]:
        """Every workflow a project can use, each described as a project's is."""

        roles, workflows = self.workflow_catalogue()
        return {"workflows": [describe_workflow(wf, roles) for wf in workflows.values()]}

    def list_roles(self) -> dict[str, Any]:
        """Return all available role definitions."""

        try:
            roles = workspace_definitions(self.store).roles
        except (RoleLoadError, WorkflowLoadError) as exc:
            raise ActionFailedError(f"Failed to load roles: {exc}") from exc
        return {"roles": [_serialize_role(role) for role in roles.values()]}

    def get_project_definitions(self, project_id: str | None) -> dict[str, Any]:
        """The roles and workflows a project runs with, as the editor shows them.

        ``None`` is the workspace: the defaults every project starts from.
        """

        if project_id is not None:
            self._require_project(project_id)
        try:
            return describe_project_definitions(self.store, project_id)
        except (RoleLoadError, WorkflowLoadError) as exc:
            raise InvalidRequestError(f"The definitions do not load: {exc}") from exc

    def save_project_definition(
        self,
        project_id: str | None,
        kind: str,
        definition_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Save one role or workflow, for a project or the workspace, from the editor."""

        if project_id is not None:
            self._require_project(project_id)
        changed_by = str(body.get("requested_by") or "").strip() or "dashboard"
        try:
            save_from_dashboard(
                self.store, project_id, kind, definition_id, body, changed_by=changed_by
            )
        except DefinitionError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self.get_project_definitions(project_id)

    def reset_project_definition(
        self, project_id: str | None, kind: str, definition_id: str, *, requested_by: str | None = None
    ) -> dict[str, Any]:
        """Drop a scope's own role or workflow; the id goes back to the layer below."""

        if project_id is not None:
            self._require_project(project_id)
        try:
            reset_from_dashboard(
                self.store, project_id, kind, definition_id, changed_by=requested_by or "dashboard"
            )
        except DefinitionError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self.get_project_definitions(project_id)
