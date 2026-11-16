"""A project's roles and workflows as the dashboard shows and edits them (ADR-0024).

The dashboard edits a form; what is stored is TOML text. This module turns a
definition into the form's fields and the fields back into text, starting
from the text the definition already has so that what the form does not show
(a role's flags, a workflow's cost and time gates) is kept as it was.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import tomlkit

from .definitions import (
    ROLE,
    WORKFLOW,
    DefinitionError,
    ProjectDefinitions,
    project_definitions,
    remove_definition,
    save_role,
    save_workflow,
)
from .outcomes import CANONICAL_OUTCOMES
from .roles import KNOWN_TOOLS, RoleDefinition
from .settings import settings_of
from .workflows import _BUILTIN_OUTCOMES, WorkflowDefinition

DECISIONS: tuple[str, ...] = ("approve", "deny", "steer", "escalate")
DEFAULT_MARKER = "TASK_COMPLETE"

#: The steps the engine does itself, in the order the editor offers them.
ENGINE_STEPS: tuple[tuple[str, str], ...] = (
    ("_builtin:run_tests", "The tests"),
    ("_builtin:human_gate", "A person"),
    ("_builtin:merge", "The merge"),
    ("_builtin:mark_done", "Mark the task done"),
)
_OUTCOME_ORDER = ("done", "success", "approve", "deny", "steer", "escalate", "failure", "conflict", "blocked", "error")
_COMPLETION = "completion:"


def _origin(definition_id: str, own: Mapping[str, str], shipped: frozenset[str]) -> str:
    if definition_id not in own:
        return "shipped"
    return "changed" if definition_id in shipped else "own"


def _text(definition_id: str, own: Mapping[str, str], source_path: Path) -> str:
    text = own.get(definition_id)
    return text if text is not None else Path(source_path).read_text(encoding="utf-8")


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
        "text": _text(role.id, definitions.own_roles, role.source_path),
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
    workflow: WorkflowDefinition, definitions: ProjectDefinitions, used: bool
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
        "used": used,
        "steps": [
            {
                "id": step.id,
                "role": step.role,
                "policy": step.policy,
                "then": then.get(step.id, {}),
            }
            for step in workflow.steps
        ],
        "text": _text(workflow.id, definitions.own_workflows, workflow.source_path),
    }


def describe_project_definitions(store, project_id: str) -> dict[str, Any]:
    """Everything the editor needs: the project's roles, workflows and the words to choose from."""

    project = store.get_project(project_id)
    definitions = project_definitions(store, project_id)
    models: list[str] = []
    for model in [settings_of(project).default_model, *(role.agent.model for role in definitions.roles.values())]:
        if model and model not in models:
            models.append(model)
    done_by = [
        {"role": role_id, "label": label, "outcomes": _step_outcomes(role_id, definitions.roles)}
        for role_id, label in ENGINE_STEPS
    ] + [
        {"role": role.id, "label": role.name, "outcomes": _step_outcomes(role.id, definitions.roles)}
        for role in definitions.roles.values()
    ]
    return {
        "roles": [_describe_role(role, definitions) for role in definitions.roles.values()],
        "workflows": [
            _describe_workflow(workflow, definitions, used=workflow.id == project.workflow_id)
            for workflow in definitions.workflows.values()
        ],
        "vocabulary": {
            "tools": {backend: list(names) for backend, names in KNOWN_TOOLS.items()},
            "decisions": list(DECISIONS),
            "models": models,
            "default_model": settings_of(project).default_model or "",
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


def role_text_from_fields(base_text: str, role_id: str, fields: Mapping[str, Any]) -> str:
    """Return ``base_text`` with the form's fields written into it."""

    doc = tomlkit.parse(base_text)
    role, agent, completion = _table(doc, "role"), _table(doc, "agent"), _table(doc, "completion")
    role["id"] = role_id
    role["name"] = _string(fields, "name").strip()
    role["description"] = _string(fields, "description").strip()
    if not role["name"]:
        raise DefinitionError("A role needs a name.")
    agent["model"] = _string(fields, "model").strip()

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
    source = definition_id if definition_id in loaded else copy_of
    if source is None or source not in loaded:
        raise DefinitionError(
            f"There is no {kind} {definition_id!r} yet. A new {kind} starts as a copy: say which one."
        )
    return _text(source, own, loaded[source].source_path)


def save_from_dashboard(
    store, project_id: str, kind: str, definition_id: str, body: Mapping[str, Any], *, changed_by: str
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

    save = save_role if kind == ROLE else save_workflow
    saved = save(store, project_id, text, changed_by=changed_by, expected_id=definition_id)
    return {"id": saved.id}


def reset_from_dashboard(
    store, project_id: str, kind: str, definition_id: str, *, changed_by: str
) -> dict[str, Any]:
    left = remove_definition(store, project_id, kind, definition_id, changed_by=changed_by)
    return {"id": definition_id, "shipped": left}
