"""Roles and workflows in three layers: shipped, the workspace's, a project's.

Foreman ships roles and workflows as TOML files. The workspace may keep its
own text under any id (ADR-0024): that is the default every project starts
from. A project may keep its own over that. One with an id from the layer
below replaces it; one with a new id adds to it. Everything that runs or
shows a project's work reads its definitions through
:func:`project_definitions`; what has no project reads
:func:`workspace_definitions`.

Wherever a function takes ``project_id``, ``None`` means the workspace.

A save is refused unless every set it reaches still loads afterwards, so
no project is left with a workflow that names a missing role or an outcome
its role cannot produce.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..domain.errors import ForemanError
from ..domain.models import utc_now_text
from ..store import ForemanStore
from .roles import RoleDefinition, RoleLoadError, branch_role_ids, load_role_text, load_roles
from .workflows import (
    WorkflowDefinition,
    WorkflowLoadError,
    load_workflow_text,
    load_workflows,
)

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
    #: Ids this scope keeps its own text for, and that text.
    own_roles: dict[str, str] = field(default_factory=dict)
    own_workflows: dict[str, str] = field(default_factory=dict)
    #: Ids the layers below define (whether or not this scope replaced them):
    #: what Foreman ships and, for a project, what the workspace keeps.
    shipped_roles: frozenset[str] = frozenset()
    shipped_workflows: frozenset[str] = frozenset()
    #: The workspace's text under a project's: what "back to the default" restores.
    default_roles: dict[str, str] = field(default_factory=dict)
    default_workflows: dict[str, str] = field(default_factory=dict)


def _source(project_id: str | None, kind: str, definition_id: str) -> str:
    if project_id is None:
        return f"{kind} {definition_id!r} of the workspace"
    return f"{kind} {definition_id!r} of project {project_id!r}"


def _role_outcomes(roles: dict[str, RoleDefinition]) -> dict[str, tuple[str, ...]]:
    return {role_id: role.completion.outcomes for role_id, role in roles.items()}


Texts = tuple[dict[str, str], dict[str, str]]


def _assemble(project_id: str | None, own: Texts, default: Texts = ({}, {})) -> ProjectDefinitions:
    """Load the shipped definitions and lay the given texts over them.

    ``default`` is the workspace's texts under a project's ``own``; for the
    workspace itself there is nothing between it and what is shipped.
    """

    own_roles, own_workflows = own
    default_roles, default_workflows = default

    def lay_roles(scope: str | None, texts: dict[str, str]) -> None:
        for role_id, text in texts.items():
            role = load_role_text(text, _source(scope, ROLE, role_id))
            if role.id != role_id:
                raise RoleLoadError(
                    f"{_source(scope, ROLE, role_id)}: the file says its id is {role.id!r}."
                )
            roles[role_id] = role

    def lay_workflows(scope: str | None, texts: dict[str, str]) -> None:
        for workflow_id, text in texts.items():
            workflow = load_workflow_text(
                text,
                _source(scope, WORKFLOW, workflow_id),
                available_role_ids=set(roles),
                role_outcomes=outcomes,
                branch_roles=branch_role_ids(roles),
            )
            if workflow.id != workflow_id:
                raise WorkflowLoadError(
                    f"{_source(scope, WORKFLOW, workflow_id)}: the file says its id is {workflow.id!r}."
                )
            workflows[workflow_id] = workflow

    roles = load_roles()
    lay_roles(None, default_roles)
    below_roles = frozenset(roles)
    lay_roles(project_id, own_roles)

    outcomes = _role_outcomes(roles)
    workflows = load_workflows(
        available_role_ids=set(roles), role_outcomes=outcomes, branch_roles=branch_role_ids(roles)
    )
    lay_workflows(None, default_workflows)
    below_workflows = frozenset(workflows)
    lay_workflows(project_id, own_workflows)

    return ProjectDefinitions(
        roles=roles,
        workflows=workflows,
        own_roles=dict(own_roles),
        own_workflows=dict(own_workflows),
        shipped_roles=below_roles,
        shipped_workflows=below_workflows,
        default_roles=dict(default_roles),
        default_workflows=dict(default_workflows),
    )


def _own_texts(store: ForemanStore, project_id: str | None) -> Texts:
    own_roles: dict[str, str] = {}
    own_workflows: dict[str, str] = {}
    for stored in store.current_definitions(project_id):
        (own_roles if stored.kind == ROLE else own_workflows)[stored.definition_id] = stored.body
    return own_roles, own_workflows


def _default_texts(store: ForemanStore, project_id: str | None) -> Texts:
    """What lies between the shipped files and this scope: the workspace's, under a project."""

    return ({}, {}) if project_id is None else _own_texts(store, None)


def project_definitions(store: ForemanStore, project_id: str | None) -> ProjectDefinitions:
    """Return the roles and workflows a project runs with (the workspace's for ``None``).

    Raises :class:`RoleLoadError` or :class:`WorkflowLoadError` when a
    definition does not load.
    """

    return _assemble(project_id, _own_texts(store, project_id), _default_texts(store, project_id))


def workspace_definitions(store: ForemanStore) -> ProjectDefinitions:
    """The defaults: what Foreman ships with the workspace's own over it."""

    return project_definitions(store, None)


def _checked(store: ForemanStore, project_id: str | None, own: Texts) -> ProjectDefinitions:
    """Load the scope with these texts, and every project a workspace change reaches."""

    try:
        definitions = _assemble(project_id, own, _default_texts(store, project_id))
    except (RoleLoadError, WorkflowLoadError) as exc:
        raise DefinitionError(str(exc)) from exc
    if project_id is None:
        for project in store.list_projects():
            try:
                theirs = _assemble(project.id, _own_texts(store, project.id), own)
            except (RoleLoadError, WorkflowLoadError) as exc:
                raise DefinitionError(
                    f"Project {project.id!r} would no longer load with this change: {exc}"
                ) from exc
            if project.workflow_id not in theirs.workflows:
                raise DefinitionError(
                    f"Project {project.id!r} uses workflow {project.workflow_id!r}. "
                    "Change the project's workflow first."
                )
    return definitions


def _require_project(store: ForemanStore, project_id: str | None):
    if project_id is None:
        return None
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
        # "ask" is a question in a record, not a decision on a line of its own.
        missing = [
            word.upper()
            for word in role.completion.outcomes
            if word != "ask" and word.upper() not in prompt
        ]
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
    project_id: str | None,
    text: str,
    *,
    changed_by: str,
    expected_id: str | None = None,
    check_model: Callable[[str, str], str | None] | None = None,
) -> RoleDefinition:
    """Save a role for one project or the workspace, under the id the text gives.

    ``check_model(backend, model)`` says why the agent program cannot run a
    model, or ``None``. It is asked when the save names a model the role did
    not have before, and its answer refuses the save.
    """

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
    definitions = _checked(store, project_id, (own_roles, own_workflows))
    if check_model is not None:
        before = project_definitions(store, project_id).roles.get(role.id)
        known = set()
        if before is not None and before.agent.backend == role.agent.backend:
            known = {before.agent.model, *before.agent.model_ladder}
        for model in dict.fromkeys((role.agent.model, *role.agent.model_ladder)):
            if model and model not in known:
                problem = check_model(role.agent.backend, model)
                if problem:
                    raise DefinitionError(problem)
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
    project_id: str | None,
    text: str,
    *,
    changed_by: str,
    expected_id: str | None = None,
) -> WorkflowDefinition:
    """Save a workflow for one project or the workspace, under the id the text gives."""

    _require_project(store, project_id)
    own_roles, own_workflows = _own_texts(store, project_id)
    current = _checked(store, project_id, (own_roles, own_workflows))
    try:
        workflow = load_workflow_text(
            text,
            "the workflow",
            available_role_ids=set(current.roles),
            role_outcomes=_role_outcomes(current.roles),
            branch_roles=branch_role_ids(current.roles),
        )
    except WorkflowLoadError as exc:
        raise DefinitionError(str(exc)) from exc
    _check_expected(WORKFLOW, workflow.id, expected_id)
    if not _ID_RE.match(workflow.id):
        raise DefinitionError(
            f"A workflow id is lower-case letters, digits and underscores, starting with a letter; got {workflow.id!r}."
        )
    own_workflows[workflow.id] = text
    definitions = _checked(store, project_id, (own_roles, own_workflows))
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
    store: ForemanStore, project_id: str | None, kind: str, definition_id: str, *, changed_by: str
) -> bool:
    """Drop the scope's own text for one definition.

    An id the layer below defines goes back to that definition; any other
    id is gone. Returns whether a definition is left under the id.
    """

    project = _require_project(store, project_id)
    own_roles, own_workflows = _own_texts(store, project_id)
    own = own_roles if kind == ROLE else own_workflows
    if definition_id not in own:
        keeper = "The workspace" if project_id is None else f"Project {project_id!r}"
        raise DefinitionError(f"{keeper} keeps no {kind} of its own called {definition_id!r}.")
    del own[definition_id]
    definitions = _checked(store, project_id, (own_roles, own_workflows))
    left = definition_id in (definitions.roles if kind == ROLE else definitions.workflows)
    if project is not None and kind == WORKFLOW and not left and project.workflow_id == definition_id:
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
