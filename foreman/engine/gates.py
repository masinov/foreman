"""Policy decisions at workflow gates and what to say when a step dead-ends."""

from __future__ import annotations

from ..models import Project, Task
from ..policy import GATE_DECISIONS, PolicyMatrix
from ..workflows import WorkflowDefinition, WorkflowStep


def gate_policy_decision(
    project: Project,
    task: Task,
    step: WorkflowStep,
) -> str:
    """Return ``auto`` or ``human`` for one human-gate step.

    The answer comes from the project's policy matrix, which resolves the
    step's policy from the task's overrides, the rule for its task type,
    and the project default, in that order. Gate steps that name no
    policy are not part of the matrix and always require a person.
    """

    policy = step.policy
    if not policy or policy not in GATE_DECISIONS:
        return "human"
    return (
        PolicyMatrix.for_project(project)
        .resolve(policy, task_type=task.task_type, overrides=task.executor_overrides)
        .value
    )


def blocked_reason_for_unhandled_outcome(
    *,
    workflow: WorkflowDefinition,
    step: str,
    outcome: str,
    detail: str | None,
) -> str:
    """Return the task block reason for a step outcome with no transition."""

    if outcome in {"error", "killed", "blocked"} and detail:
        return detail
    if workflow.fallback is not None:
        return workflow.fallback.message
    return f"No transition for '{outcome}' at '{step}'"
