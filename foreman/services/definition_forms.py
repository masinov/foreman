"""A project's roles and workflows as the dashboard shows and edits them (ADR-0024).

The dashboard edits a form; what is stored is TOML text. This module turns a
definition into the form's fields and the fields back into text, starting
from the text the definition already has so that what the form does not show
(a role's flags, a workflow's cost and time gates) is kept as it was.
"""

from __future__ import annotations

from dataclasses import replace

from pathlib import Path
from typing import Any, Mapping

import tomlkit

from ..definitions.layers import (
    ROLE,
    WORKFLOW,
    DefinitionError,
    ProjectDefinitions,
    project_definitions,
    remove_definition,
    save_role,
    save_workflow,
)
from ..runner.model_check import check_model
from ..domain.outcomes import CANONICAL_OUTCOMES
from ..definitions.roles import DEFAULT_ESCALATE_AFTER, KNOWN_TOOLS, RoleDefinition, load_role_text
from ..domain.settings import settings_of
from ..definitions.workflows import _BUILTIN_OUTCOMES, WorkflowDefinition, load_workflow_text

DECISIONS: tuple[str, ...] = ("approve", "deny", "steer", "escalate")
DEFAULT_MARKER = "TASK_COMPLETE"

#: The steps the engine does itself, in the order the editor offers them.
ENGINE_STEPS: tuple[tuple[str, str], ...] = (
    ("_builtin:run_tests", "The tests"),
    ("_builtin:human_gate", "A user"),
    ("_builtin:merge", "The merge"),
    ("_builtin:mark_done", "Mark the task done"),
)
_OUTCOME_ORDER = ("done", "success", "approve", "deny", "steer", "escalate", "failure", "conflict", "updated", "blocked", "error")
_COMPLETION = "completion:"

#: What a new definition is a copy of when it starts empty.
BLANK = "_blank"

#: Models offered for a backend besides the ones the roles already name.
_KNOWN_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")

_BLANK_ROLE = '''[role]
id = "new_role"
name = "New role"
description = ""

[agent]
backend = "claude_code"
model = ""
session_persistence = true
permission_mode = "bypassPermissions"

[agent.tools]
allowed = []
disallowed = []

[prompt]
template = """
## Task: {task_title}
Branch: {branch_name}

### Description
{task_description}

### Acceptance criteria
{acceptance_criteria}

### What the step before this one said
{previous_feedback}

### Repository instructions
{repo_instructions}

Say here what this role does with the task.

When you are finished, end your message with:
{completion_marker}
"""

[completion]
marker = "TASK_COMPLETE"
timeout_minutes = 30
max_cost_usd = 10.0

[completion.output]
extract_summary = true
'''

_BLANK_WORKFLOW = '''[workflow]
id = "new_workflow"
name = "New workflow"
methodology = "development"

[[steps]]
id = "develop"
role = "developer"

[[steps]]
id = "test"
role = "_builtin:run_tests"

[[steps]]
id = "review"
role = "code_reviewer"

[[steps]]
id = "merge"
role = "_builtin:merge"

[[steps]]
id = "done"
role = "_builtin:mark_done"

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "test"

[[transitions]]
from = "test"
trigger = "completion:success"
to = "review"

[[transitions]]
from = "test"
trigger = "completion:failure"
to = "develop"
carry_output = true

[[transitions]]
from = "review"
trigger = "completion:approve"
to = "merge"

[[transitions]]
from = "review"
trigger = "completion:deny"
to = "develop"
carry_output = true

[[transitions]]
from = "review"
trigger = "completion:steer"
to = "develop"
carry_output = true

[[transitions]]
from = "merge"
trigger = "completion:success"
to = "done"

[[transitions]]
from = "merge"
trigger = "completion:failure"
to = "develop"
carry_output = true

[[transitions]]
from = "merge"
trigger = "completion:conflict"
to = "develop"
carry_output = true

[[transitions]]
from = "merge"
trigger = "completion:updated"
to = "test"
'''


def _origin(definition_id: str, own: Mapping[str, str], shipped: frozenset[str]) -> str:
    if definition_id not in own:
        return "shipped"
    return "changed" if definition_id in shipped else "own"


def _text(definition_id: str, own: Mapping[str, str], default: Mapping[str, str], source_path: Path) -> str:
    """The text in force: the scope's own, else the workspace's, else the shipped file."""

    for texts in (own, default):
        if definition_id in texts:
            return texts[definition_id]
    return Path(source_path).read_text(encoding="utf-8")


def _tools(role: RoleDefinition) -> dict[str, Any]:
    known = KNOWN_TOOLS.get(role.agent.backend, ())
    allowed, disallowed = role.agent.tools.allowed, role.agent.tools.disallowed
    if role.agent.tools.none:
        return {"every": False, "chosen": []}
    return {
        "every": not allowed and not disallowed,
        "chosen": [name for name in known if (not allowed or name in allowed) and name not in disallowed],
    }


def _describe_role(role: RoleDefinition, definitions: ProjectDefinitions) -> dict[str, Any]:
    decides = role.completion.output.extract_decision
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "backend": role.agent.backend,
        "model": role.agent.model,
        # Its models, cheapest first; none means the project's default.
        "models": list(role.agent.model_ladder) or ([role.agent.model] if role.agent.model else []),
        "escalate_after": role.agent.escalate_after,
        "tools": _tools(role),
        "ends": "decides" if decides else "done",
        "decisions": [word for word in DECISIONS if decides and word in role.completion.outcomes],
        "marker": role.completion.marker,
        "timeout_minutes": role.completion.timeout_minutes,
        "max_cost_usd": role.completion.max_cost_usd,
        "prompt": role.prompt_template,
        "origin": _origin(role.id, definitions.own_roles, definitions.shipped_roles),
        "used_by": [
            workflow.name
            for workflow in definitions.workflows.values()
            if any(step.role == role.id for step in workflow.steps)
        ],
        "text": _text(role.id, definitions.own_roles, definitions.default_roles, role.source_path),
    }


def _step_outcomes(role_id: str, roles: Mapping[str, RoleDefinition]) -> list[str]:
    """The ways a step can end that a workflow may route, in a fixed order."""

    if role_id in _BUILTIN_OUTCOMES:
        found = _BUILTIN_OUTCOMES[role_id]
    elif role_id in roles:
        role = roles[role_id]
        # An agent that does not decide ends "done"; its blocker and error
        # stop the task and are not routed.
        found = set(role.completion.outcomes) if role.completion.output.extract_decision else {"done"}
    else:
        found = set()
    return [outcome for outcome in _OUTCOME_ORDER if outcome in found]


def _describe_workflow(
    workflow: WorkflowDefinition, definitions: ProjectDefinitions, used_by: list[str]
) -> dict[str, Any]:
    then: dict[str, dict[str, Any]] = {}
    for transition in workflow.transitions:
        if transition.trigger.startswith(_COMPLETION):
            then.setdefault(transition.from_step, {})[transition.trigger[len(_COMPLETION):]] = {
                "to": transition.to_step,
                "carry_output": transition.carry_output,
            }
    return {
        "id": workflow.id,
        "name": workflow.name,
        "origin": _origin(workflow.id, definitions.own_workflows, definitions.shipped_workflows),
        "used": bool(used_by),
        "used_by": used_by,
        "steps": [
            {
                "id": step.id,
                "role": step.role,
                "policy": step.policy,
                "then": then.get(step.id, {}),
            }
            for step in workflow.steps
        ],
        "text": _text(workflow.id, definitions.own_workflows, definitions.default_workflows, workflow.source_path),
    }


def _describe_blank(definitions: ProjectDefinitions) -> dict[str, Any]:
    """The empty role, and the shortest workflow that can finish a task, to start a new one from."""

    role = load_role_text(_BLANK_ROLE, "the empty role")
    workflow = load_workflow_text(
        _BLANK_WORKFLOW,
        "the empty workflow",
        available_role_ids=set(definitions.roles),
        role_outcomes={role_id: r.completion.outcomes for role_id, r in definitions.roles.items()},
    )
    with_blank = replace(
        definitions,
        own_roles={**definitions.own_roles, role.id: _BLANK_ROLE},
        own_workflows={**definitions.own_workflows, workflow.id: _BLANK_WORKFLOW},
    )
    return {
        "role": {**_describe_role(role, with_blank), "id": BLANK, "name": "", "used_by": []},
        "workflow": {**_describe_workflow(workflow, with_blank, []), "id": BLANK, "name": ""},
    }


def describe_project_definitions(store, project_id: str | None) -> dict[str, Any]:
    """Everything the editor needs: the roles, workflows and the words to choose from.

    For a project, what it runs with; for ``None``, the workspace's defaults,
    each workflow with the projects that use it.
    """

    definitions = project_definitions(store, project_id)
    if project_id is None:
        default_model = ""
        users = store.list_projects()
    else:
        project = store.get_project(project_id)
        default_model = settings_of(project).default_model or ""
        users = [project]
    models: list[str] = []
    named = [model for role in definitions.roles.values() for model in (role.agent.model, *role.agent.model_ladder)]
    for model in [default_model, *named]:
        if model and model not in models:
            models.append(model)
    done_by = [
        {"role": role_id, "label": label, "outcomes": _step_outcomes(role_id, definitions.roles)}
        for role_id, label in ENGINE_STEPS
    ] + [
        {"role": role.id, "label": role.name, "outcomes": _step_outcomes(role.id, definitions.roles)}
        for role in definitions.roles.values()
    ]
    for model in _KNOWN_MODELS:
        if model not in models:
            models.append(model)
    return {
        "blank": _describe_blank(definitions),
        "roles": [_describe_role(role, definitions) for role in definitions.roles.values()],
        "workflows": [
            _describe_workflow(
                workflow, definitions, [user.name for user in users if user.workflow_id == workflow.id]
            )
            for workflow in definitions.workflows.values()
        ],
        "vocabulary": {
            "tools": {backend: list(names) for backend, names in KNOWN_TOOLS.items()},
            "decisions": list(DECISIONS),
            "models": models,
            "default_model": default_model,
            "done_by": done_by,
            "gate_policies": ["merge_approval", "plan_approval"],
        },
    }


# ── fields back into text ───────────────────────────────────────────────────


def _table(parent, key: str):
    if key not in parent:
        parent[key] = tomlkit.table()
    return parent[key]


def _string(fields: Mapping[str, Any], key: str) -> str:
    value = fields.get(key, "")
    if not isinstance(value, str):
        raise DefinitionError(f"'{key}' must be text.")
    return value


def _names(value: Any, key: str, allowed: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DefinitionError(f"'{key}' must be a list of names.")
    unknown = [item for item in value if item not in allowed]
    if unknown:
        raise DefinitionError(f"'{key}' has unknown name(s): {', '.join(unknown)}.")
    return [item for item in allowed if item in value]


def _role_models(fields: Mapping[str, Any]) -> list[str]:
    """The models the form names, cheapest first (an older form names one ``model``)."""

    if "models" not in fields:
        single = _string(fields, "model").strip()
        return [single] if single else []
    models = fields["models"]
    if not isinstance(models, list) or any(not isinstance(item, str) for item in models):
        raise DefinitionError("'models' must be a list of model ids.")
    cleaned = [item.strip() for item in models if item.strip()]
    if len(set(cleaned)) != len(cleaned):
        raise DefinitionError("A model is listed once; a step moves up to a different model.")
    return cleaned


def role_text_from_fields(base_text: str, role_id: str, fields: Mapping[str, Any]) -> str:
    """Return ``base_text`` with the form's fields written into it."""

    doc = tomlkit.parse(base_text)
    role, agent, completion = _table(doc, "role"), _table(doc, "agent"), _table(doc, "completion")
    role["id"] = role_id
    role["name"] = _string(fields, "name").strip()
    role["description"] = _string(fields, "description").strip()
    if not role["name"]:
        raise DefinitionError("A role needs a name.")
    models = _role_models(fields)
    agent["model"] = models[0] if models else ""
    # One model never moves up, so it is the role's model and no ladder.
    if len(models) > 1:
        agent["model_ladder"] = models
    else:
        agent.pop("model_ladder", None)
    escalate_after = fields.get("escalate_after", DEFAULT_ESCALATE_AFTER)
    if isinstance(escalate_after, bool) or not isinstance(escalate_after, int) or escalate_after < 1:
        raise DefinitionError(
            "The failures before a step moves up to the next model are a whole number, 1 or more."
        )
    if len(models) > 1 or "escalate_after" in agent:
        agent["escalate_after"] = escalate_after

    tools = fields.get("tools") or {}
    known = KNOWN_TOOLS.get(str(agent.get("backend", "")), ())
    tools_table = _table(agent, "tools")
    chosen = [] if tools.get("every") else _names(tools.get("chosen", []), "tools", known)
    tools_table["allowed"] = chosen
    tools_table["disallowed"] = []
    # An empty allowed list means every tool, so having none is said outright.
    if tools.get("every") or chosen:
        tools_table.pop("none", None)
    else:
        tools_table["none"] = True

    _table(doc, "prompt")["template"] = tomlkit.string(_string(fields, "prompt"), multiline=True)

    output = _table(completion, "output")
    ends = fields.get("ends")
    if ends == "decides":
        decisions = _names(fields.get("decisions", []), "decisions", DECISIONS)
        if not decisions:
            raise DefinitionError("A role that decides needs at least one decision it may give.")
        completion["marker"] = ""
        completion["outcomes"] = decisions
        output["extract_decision"] = True
    elif ends == "done":
        completion["marker"] = str(completion.get("marker") or "") or DEFAULT_MARKER
        completion.pop("outcomes", None)
        output["extract_decision"] = False
        output.pop("approve_needs_reading", None)
    else:
        raise DefinitionError("'ends' must be 'done' or 'decides'.")

    timeout, cost = fields.get("timeout_minutes"), fields.get("max_cost_usd")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise DefinitionError("The time limit must be a whole number of minutes above zero.")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost <= 0:
        raise DefinitionError("The cost limit must be a number above zero.")
    completion["timeout_minutes"] = timeout
    completion["max_cost_usd"] = float(cost)
    return tomlkit.dumps(doc)


def workflow_text_from_fields(base_text: str, workflow_id: str, fields: Mapping[str, Any]) -> str:
    """Return a workflow's text from the form's steps, keeping the base's gates and fallback."""

    base = tomlkit.parse(base_text)
    name = _string(fields, "name").strip()
    if not name:
        raise DefinitionError("A workflow needs a name.")
    steps = fields.get("steps")
    if not isinstance(steps, list) or not steps:
        raise DefinitionError("A workflow needs at least one step.")

    doc = tomlkit.document()
    workflow = tomlkit.table()
    workflow["id"] = workflow_id
    workflow["name"] = name
    workflow["methodology"] = str(base.get("workflow", {}).get("methodology", "development"))
    doc["workflow"] = workflow

    step_tables, transition_tables = tomlkit.aot(), tomlkit.aot()
    for step in steps:
        if not isinstance(step, dict):
            raise DefinitionError("Each step must be an object.")
        step_id = str(step.get("id", "")).strip()
        table = tomlkit.table()
        table["id"] = step_id
        table["role"] = str(step.get("role", "")).strip()
        if step.get("policy"):
            table["policy"] = str(step["policy"])
        step_tables.append(table)
        for outcome, target in (step.get("then") or {}).items():
            if outcome not in CANONICAL_OUTCOMES:
                raise DefinitionError(f"Step {step_id!r}: {outcome!r} is not a way a step can end.")
            if not isinstance(target, dict) or not target.get("to"):
                continue
            transition = tomlkit.table()
            transition["from"] = step_id
            transition["trigger"] = f"{_COMPLETION}{outcome}"
            transition["to"] = str(target["to"])
            if target.get("carry_output"):
                transition["carry_output"] = True
            transition_tables.append(transition)
    doc["steps"] = step_tables
    if len(transition_tables):
        doc["transitions"] = transition_tables
    for key in ("gates", "fallback"):
        if key in base:
            doc[key] = base[key]
    return tomlkit.dumps(doc)


def _base_text(kind: str, definitions: ProjectDefinitions, definition_id: str, copy_of: str | None) -> str:
    loaded = definitions.roles if kind == ROLE else definitions.workflows
    own = definitions.own_roles if kind == ROLE else definitions.own_workflows
    if definition_id not in loaded and copy_of == BLANK:
        return _BLANK_ROLE if kind == ROLE else _BLANK_WORKFLOW
    source = definition_id if definition_id in loaded else copy_of
    if source is None or source not in loaded:
        raise DefinitionError(
            f"There is no {kind} {definition_id!r} yet. A new {kind} starts as a copy: say which one."
        )
    default = definitions.default_roles if kind == ROLE else definitions.default_workflows
    return _text(source, own, default, loaded[source].source_path)


def save_from_dashboard(
    store, project_id: str | None, kind: str, definition_id: str, body: Mapping[str, Any], *, changed_by: str
) -> dict[str, Any]:
    """Save one role or workflow from the editor: its text, or its form fields."""

    if kind not in (ROLE, WORKFLOW):
        raise DefinitionError(f"Unknown kind {kind!r}.")
    if isinstance(body.get("text"), str):
        text = body["text"]
    elif isinstance(body.get("fields"), dict):
        definitions = project_definitions(store, project_id)
        base = _base_text(kind, definitions, definition_id, body.get("copy_of"))
        build = role_text_from_fields if kind == ROLE else workflow_text_from_fields
        text = build(base, definition_id, body["fields"])
    else:
        raise DefinitionError("Send either 'text' or 'fields'.")

    if kind == ROLE:
        saved = save_role(
            store, project_id, text, changed_by=changed_by, expected_id=definition_id, check_model=check_model
        )
    else:
        saved = save_workflow(store, project_id, text, changed_by=changed_by, expected_id=definition_id)
    return {"id": saved.id}


def reset_from_dashboard(
    store, project_id: str | None, kind: str, definition_id: str, *, changed_by: str
) -> dict[str, Any]:
    left = remove_definition(store, project_id, kind, definition_id, changed_by=changed_by)
    return {"id": definition_id, "shipped": left}
