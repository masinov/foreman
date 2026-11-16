"""A project's roles and workflows: the shipped ones, with the project's own over them.

Foreman ships roles and workflows as TOML files. A project may keep its own
under any id, as TOML text in the database (ADR-0024): one with a shipped id
replaces the shipped definition for that project, one with a new id adds to
them. Everything that runs or shows a project's work reads its definitions
through :func:`project_definitions`.

A save is refused unless the whole set still loads afterwards, so a project
is never left with a workflow that names a missing role or an outcome its
role cannot produce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .errors import ForemanError
from .models import utc_now_text
from .roles import RoleDefinition, RoleLoadError, load_role_text, load_roles
from .workflows import WorkflowDefinition, WorkflowLoadError, load_workflow_text, load_workflows

if TYPE_CHECKING:
    from .store import ForemanStore

ROLE = "role"
WORKFLOW = "workflow"

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class DefinitionError(ForemanError):
    """A role or workflow that cannot be saved or removed, with the reason."""


@dataclass(slots=True)
class ProjectDefinitions:
    """What one project runs with, and which of it is the project's own."""

    roles: dict[str, RoleDefinition]
    workflows: dict[str, WorkflowDefinition]
    #: Ids the project keeps its own text for, and that text.
    own_roles: dict[str, str] = field(default_factory=dict)
    own_workflows: dict[str, str] = field(default_factory=dict)
    #: Ids Foreman ships (whether or not the project replaced them).
    shipped_roles: frozenset[str] = frozenset()
    shipped_workflows: frozenset[str] = frozenset()


def _source(project_id: str, kind: str, definition_id: str) -> str:
    return f"{kind} {definition_id!r} of project {project_id!r}"


def _role_outcomes(roles: dict[str, RoleDefinition]) -> dict[str, tuple[str, ...]]:
    return {role_id: role.completion.outcomes for role_id, role in roles.items()}


def _assemble(
    project_id: str, own_roles: dict[str, str], own_workflows: dict[str, str]
) -> ProjectDefinitions:
    """Load the shipped definitions and lay the given texts over them."""

    roles = load_roles()
    shipped_roles = frozenset(roles)
    for role_id, text in own_roles.items():
        role = load_role_text(text, _source(project_id, ROLE, role_id))
        if role.id != role_id:
            raise RoleLoadError(
                f"{_source(project_id, ROLE, role_id)}: the file says its id is {role.id!r}."
            )
        roles[role_id] = role

    outcomes = _role_outcomes(roles)
    workflows = load_workflows(available_role_ids=set(roles), role_outcomes=outcomes)
    shipped_workflows = frozenset(workflows)
    for workflow_id, text in own_workflows.items():
        workflow = load_workflow_text(
            text,
            _source(project_id, WORKFLOW, workflow_id),
            available_role_ids=set(roles),
            role_outcomes=outcomes,
        )
        if workflow.id != workflow_id:
            raise WorkflowLoadError(
                f"{_source(project_id, WORKFLOW, workflow_id)}: the file says its id is {workflow.id!r}."
            )
        workflows[workflow_id] = workflow

    return ProjectDefinitions(
        roles=roles,
        workflows=workflows,
        own_roles=dict(own_roles),
        own_workflows=dict(own_workflows),
        shipped_roles=shipped_roles,
        shipped_workflows=shipped_workflows,
    )


def _own_texts(store: ForemanStore, project_id: str) -> tuple[dict[str, str], dict[str, str]]:
    own_roles: dict[str, str] = {}
    own_workflows: dict[str, str] = {}
    for stored in store.current_definitions(project_id):
        (own_roles if stored.kind == ROLE else own_workflows)[stored.definition_id] = stored.body
    return own_roles, own_workflows


def project_definitions(store: ForemanStore, project_id: str) -> ProjectDefinitions:
    """Return the roles and workflows a project runs with.

    Raises :class:`RoleLoadError` or :class:`WorkflowLoadError` when a
    definition does not load.
    """

    own_roles, own_workflows = _own_texts(store, project_id)
    return _assemble(project_id, own_roles, own_workflows)


def _checked(project_id: str, own_roles: dict[str, str], own_workflows: dict[str, str]) -> ProjectDefinitions:
    try:
        return _assemble(project_id, own_roles, own_workflows)
    except (RoleLoadError, WorkflowLoadError) as exc:
        raise DefinitionError(str(exc)) from exc


def _require_project(store: ForemanStore, project_id: str):
    project = store.get_project(project_id)
    if project is None:
        raise DefinitionError(f"Project {project_id!r} was not found.")
    return project


def _check_expected(kind: str, found: str, expected: str | None) -> None:
    if expected is not None and found != expected:
        raise DefinitionError(
            f"The text says its id is {found!r}, and this is {kind} {expected!r}. "
            f"An id is not changed by editing; save it as a new {kind} instead."
        )


def check_role_says_how_to_end(role: RoleDefinition) -> None:
    """Refuse a role whose prompt does not tell the agent how the engine reads its end.

    The engine looks for the completion marker, or for one of the role's
    decisions on a line of its own. Nothing joins that to the prompt but
    this check: an agent that is never told ends every run asked again.
    """

    prompt = role.prompt_template
    if role.completion.output.extract_decision:
        missing = [word.upper() for word in role.completion.outcomes if word.upper() not in prompt]
        if missing:
            raise DefinitionError(
                f"Role {role.id!r} may decide {', '.join(missing)} but its prompt never says so. "
                "The prompt must tell the agent to end with each decision in capitals, "
                "for example 'DENY: <reason>'."
            )
    elif role.completion.marker:
        if "{completion_marker}" not in prompt and role.completion.marker not in prompt:
            raise DefinitionError(
                f"Role {role.id!r} ends with the marker {role.completion.marker} but its prompt never "
                "says so. Tell the agent to end with {completion_marker}."
            )


def save_role(
    store: ForemanStore,
    project_id: str,
    text: str,
    *,
    changed_by: str,
    expected_id: str | None = None,
) -> RoleDefinition:
    """Save a role for one project, under the id the text gives."""

    _require_project(store, project_id)
    try:
        role = load_role_text(text, "the role")
    except RoleLoadError as exc:
        raise DefinitionError(str(exc)) from exc
    _check_expected(ROLE, role.id, expected_id)
    check_role_says_how_to_end(role)
    if not _ID_RE.match(role.id):
        raise DefinitionError(
            f"A role id is lower-case letters, digits and underscores, starting with a letter; got {role.id!r}."
        )
    own_roles, own_workflows = _own_texts(store, project_id)
    own_roles[role.id] = text
    definitions = _checked(project_id, own_roles, own_workflows)
    store.add_definition_revision(
        project_id=project_id,
        kind=ROLE,
        definition_id=role.id,
        body=text,
        removed=False,
        changed_by=changed_by,
        changed_at=utc_now_text(),
    )
    return definitions.roles[role.id]


def save_workflow(
    store: ForemanStore,
    project_id: str,
    text: str,
    *,
    changed_by: str,
    expected_id: str | None = None,
) -> WorkflowDefinition:
    """Save a workflow for one project, under the id the text gives."""

    _require_project(store, project_id)
    own_roles, own_workflows = _own_texts(store, project_id)
    current = _checked(project_id, own_roles, own_workflows)
    try:
        workflow = load_workflow_text(
            text,
            "the workflow",
            available_role_ids=set(current.roles),
            role_outcomes=_role_outcomes(current.roles),
        )
    except WorkflowLoadError as exc:
        raise DefinitionError(str(exc)) from exc
    _check_expected(WORKFLOW, workflow.id, expected_id)
    if not _ID_RE.match(workflow.id):
        raise DefinitionError(
            f"A workflow id is lower-case letters, digits and underscores, starting with a letter; got {workflow.id!r}."
        )
    own_workflows[workflow.id] = text
    definitions = _checked(project_id, own_roles, own_workflows)
    store.add_definition_revision(
        project_id=project_id,
        kind=WORKFLOW,
        definition_id=workflow.id,
        body=text,
        removed=False,
        changed_by=changed_by,
        changed_at=utc_now_text(),
    )
    return definitions.workflows[workflow.id]


def remove_definition(
    store: ForemanStore, project_id: str, kind: str, definition_id: str, *, changed_by: str
) -> bool:
    """Drop the project's own text for one definition.

    A shipped id goes back to the shipped definition; any other id is gone.
    Returns whether a shipped definition is left under the id.
    """

    project = _require_project(store, project_id)
    own_roles, own_workflows = _own_texts(store, project_id)
    own = own_roles if kind == ROLE else own_workflows
    if definition_id not in own:
        raise DefinitionError(
            f"Project {project_id!r} keeps no {kind} of its own called {definition_id!r}."
        )
    del own[definition_id]
    definitions = _checked(project_id, own_roles, own_workflows)
    left = definition_id in (definitions.roles if kind == ROLE else definitions.workflows)
    if kind == WORKFLOW and not left and project.workflow_id == definition_id:
        raise DefinitionError(
            f"Project {project_id!r} uses workflow {definition_id!r}. Change the project's workflow first."
        )
    store.add_definition_revision(
        project_id=project_id,
        kind=kind,
        definition_id=definition_id,
        body="",
        removed=True,
        changed_by=changed_by,
        changed_at=utc_now_text(),
    )
    return left
