"""A workflow definition described for the dashboard (sprint 58).

Pure reads over a loaded definition: its steps, the transitions between them,
the roles its steps name, and what finishing a task requires. Nothing here is
stored or invented; the dashboard derives "who does it", "moves on when" and
"otherwise" from these transitions, so a different definition shows different
steps and outcomes.
"""

from __future__ import annotations

from typing import Any, Mapping

from .roles import RoleDefinition
from .workflows import WorkflowDefinition

BUILTIN_PREFIX = "_builtin:"
_RUN_TESTS = "_builtin:run_tests"
_COMPLETION = "completion:"

#: What a requirement is, in the sense of ADR-0018: a fact is measured by the
#: engine, a claim is what an agent reported.
FACT = "fact"
CLAIM = "claim"


def _describe_role(role: RoleDefinition) -> dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "backend": role.agent.backend,
        # Empty means the project's default model applies.
        "model": role.agent.model,
    }


def _review_requirements(
    workflow: WorkflowDefinition, roles: Mapping[str, RoleDefinition]
) -> list[dict[str, Any]]:
    """One claim per kind of review the workflow's decision roles perform."""

    requirements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for step in workflow.steps:
        role = roles.get(step.role)
        if role is None or not role.completion.output.extract_decision:
            continue
        kind = role.completion.review_kind
        if kind in seen:
            continue
        seen.add(kind)
        steps = [
            other.id
            for other in workflow.steps
            if (r := roles.get(other.role)) is not None
            and r.completion.output.extract_decision
            and r.completion.review_kind == kind
        ]
        requirements.append(
            {
                "id": f"{kind}-review",
                "kind": CLAIM,
                "text": f"{kind.capitalize()} review approves that same commit",
                "steps": steps,
            }
        )
        if kind == "code":
            requirements.append(
                {
                    "id": "acceptance-criteria",
                    "kind": CLAIM,
                    "text": "Acceptance criteria marked met",
                    "steps": steps,
                }
            )
    return requirements


def finishing_requirements(
    workflow: WorkflowDefinition, roles: Mapping[str, RoleDefinition]
) -> list[dict[str, Any]]:
    """What a task needs before it can finish, read from the workflow's steps.

    Tests passing is a fact only when the workflow has a test step to measure
    it; each review is a claim only when a reviewing role is part of the
    workflow. A workflow without those steps requires neither.
    """

    requirements: list[dict[str, Any]] = []
    test_steps = [step.id for step in workflow.steps if step.role == _RUN_TESTS]
    if test_steps:
        requirements.append(
            {
                "id": "tests",
                "kind": FACT,
                "text": "Tests pass at the commit being merged",
                "steps": test_steps,
            }
        )
    requirements.extend(_review_requirements(workflow, roles))
    return requirements


def describe_workflow(
    workflow: WorkflowDefinition, roles: Mapping[str, RoleDefinition]
) -> dict[str, Any]:
    """The dashboard's view of one workflow definition."""

    used = []
    for step in workflow.steps:
        if step.role in roles and step.role not in used:
            used.append(step.role)
    return {
        "id": workflow.id,
        "name": workflow.name,
        "methodology": workflow.methodology,
        "source_path": str(workflow.source_path),
        "steps": [
            {"id": step.id, "role": step.role, "policy": step.policy}
            for step in workflow.steps
        ],
        "transitions": [
            {
                "from": transition.from_step,
                "trigger": transition.trigger,
                "outcome": (
                    transition.trigger[len(_COMPLETION):]
                    if transition.trigger.startswith(_COMPLETION)
                    else None
                ),
                "to": transition.to_step,
                "carry_output": transition.carry_output,
            }
            for transition in workflow.transitions
        ],
        "roles": [_describe_role(roles[role_id]) for role_id in used],
        "requirements": finishing_requirements(workflow, roles),
    }
