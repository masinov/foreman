"""Which steps of a project's workflow are human gates, and why a task is blocked.

A ``blocked`` task is either waiting at a human gate for a person's decision
or was stopped by the engine (its dead-letter state). Telling the two apart
needs the project's workflow: the steps whose role is ``_builtin:human_gate``.
The CLI, the dashboard, the engine and the rules for a person's changes all
ask this, so it is answered once, here, from the project's definitions
(ADR-0024).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from ..domain.models import Project, Task
from ..definitions.question import QUESTION_BLOCKED_REASON
from ..store import ForemanStore
from .layers import project_definitions
from .workflows import WorkflowDefinition

#: The workflow role that marks a step as a human decision point.
HUMAN_GATE_ROLE = "_builtin:human_gate"

#: The reason ``_builtin:human_gate`` writes when it parks a task. Used only as
#: a tie-breaker when the workflow definition cannot answer.
HUMAN_GATE_BLOCKED_REASON = "Awaiting human approval"

#: The two ways a task ends up ``blocked``. ``gate`` is waiting for a person and
#: is resolved with ``foreman approve``/``deny``; ``engine`` is the engine's
#: dead-letter state (loop limit, unhandled outcome, cost or time gate, branch
#: violation, failure isolation, a user's Block) and is resolved with
#: ``foreman task unblock`` or by editing the task.
#: ``question`` is an agent's question to a person (ADR-0041 section 4): the
#: task waits for an answer, resolved with ``foreman task answer``.
BLOCKED_KINDS: tuple[str, ...] = ("gate", "question", "engine")


# ── Dead-letter classification ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WorkflowGateSteps:
    """Which steps of one workflow are human gates.

    ``step_ids`` is ``None`` when the workflow could not be loaded at all (a
    missing or broken TOML file, or a project pointing at a workflow that no
    longer exists). Keeping that distinct from "loaded, and has no gate steps"
    is what lets :func:`blocked_kind` fall back to the gate builtin's own
    blocked reason instead of silently calling every gated task an engine
    failure.
    """

    step_ids: frozenset[str] | None
    gate_step_ids: frozenset[str] = frozenset()
    #: Each gate step's policy name (``plan_approval``, ``merge_approval``), or
    #: ``None`` for a gate that always waits for a person.
    gate_policies: Mapping[str, str | None] = field(default_factory=dict)
    #: The steps each gate is reached from: the step whose work it decides on
    #: (a plan approval is of the plan the step before it wrote).
    gate_sources: Mapping[str, frozenset[str]] = field(default_factory=dict)

#: Used when no workflow could be resolved for a project.
UNKNOWN_WORKFLOW = WorkflowGateSteps(step_ids=None)


def resolve_gate_steps(store: ForemanStore, project: Project | None) -> WorkflowGateSteps:
    """Return the human-gate steps of a project's workflow, tolerating load failures.

    The workflow is the project's own when it keeps one under that id
    (ADR-0024). A workflow that will not load must not take a dashboard or a
    board listing down with it, so every failure resolves to
    :data:`UNKNOWN_WORKFLOW`.
    """

    if project is None or not project.workflow_id:
        return UNKNOWN_WORKFLOW

    try:
        workflows = project_definitions(store, project.id).workflows
    except Exception:  # noqa: BLE001 - a broken definition must not hide tasks
        return UNKNOWN_WORKFLOW

    workflow = workflows.get(project.workflow_id)
    if workflow is None:
        return UNKNOWN_WORKFLOW
    return workflow_gate_steps(workflow)


def workflow_gate_steps(workflow: WorkflowDefinition) -> WorkflowGateSteps:
    """The human-gate steps of a workflow already loaded."""

    return WorkflowGateSteps(
        step_ids=frozenset(step.id for step in workflow.steps),
        gate_step_ids=frozenset(
            step.id for step in workflow.steps if step.role == HUMAN_GATE_ROLE
        ),
        gate_policies={
            step.id: step.policy
            for step in workflow.steps
            if step.role == HUMAN_GATE_ROLE
        },
        gate_sources={
            step.id: steps_into(workflow, step.id)
            for step in workflow.steps
            if step.role == HUMAN_GATE_ROLE
        },
    )


def steps_into(workflow: WorkflowDefinition, step_id: str) -> frozenset[str]:
    """The steps a workflow reaches ``step_id`` from (itself left out)."""

    return frozenset(
        transition.from_step
        for transition in workflow.transitions
        if transition.to_step == step_id and transition.from_step != step_id
    )


def blocked_kind(task: Task, gates: WorkflowGateSteps) -> str | None:
    """Classify why a task is blocked, or return None when it is not blocked.

    The task's persisted step decides: a step the project's workflow runs with
    ``_builtin:human_gate`` is a ``gate``, and anything else is the engine's
    dead-letter state. A persisted step alone is not enough — the engine also
    persists a resume point when it blocks a task after a failure — so the step
    has to be looked up in the workflow rather than merely be present.
    """

    if task.status != "blocked":
        return None
    if (task.blocked_reason or "") == QUESTION_BLOCKED_REASON:
        return "question"
    step = task.workflow_current_step
    if step and gates.step_ids is not None and step in gates.step_ids:
        return "gate" if step in gates.gate_step_ids else "engine"
    # No usable step: the gate builtin's own reason is the only signal left.
    return "gate" if (task.blocked_reason or "") == HUMAN_GATE_BLOCKED_REASON else "engine"


def blocked_kind_counts(
    tasks: Iterable[Task], gates: WorkflowGateSteps
) -> dict[str, int]:
    """Count blocked tasks by kind. Keys are always present, even at zero."""

    counts = {kind: 0 for kind in BLOCKED_KINDS}
    for task in tasks:
        kind = blocked_kind(task, gates)
        if kind is not None:
            counts[kind] += 1
    return counts


def capped_step_block(store: ForemanStore, project: Project | None, task: Task) -> str | None:
    """The step whose own cap (``max_visits``) blocks a task, or None.

    A task blocked at a capped step keeps that step as its resume point and a
    count that has reached the cap; nothing else is needed to tell it apart.
    """

    step_id = task.workflow_current_step
    if task.status != "blocked" or not step_id or project is None or not project.workflow_id:
        return None
    try:
        workflow = project_definitions(store, project.id).workflows.get(project.workflow_id)
    except Exception:  # noqa: BLE001 - a broken definition must not break unblocking
        return None
    step = workflow.get_step(step_id) if workflow is not None else None
    if step is None or step.max_visits is None:
        return None
    if task.step_visit_counts.get(step_id, 0) < step.max_visits:
        return None
    return step_id


def step_cap(store: ForemanStore, project: Project | None, step_id: str) -> int | None:
    """A step's ``max_visits``, or None."""

    if project is None or not project.workflow_id:
        return None
    workflow = project_definitions(store, project.id).workflows.get(project.workflow_id)
    step = workflow.get_step(step_id) if workflow is not None else None
    return step.max_visits if step is not None else None
