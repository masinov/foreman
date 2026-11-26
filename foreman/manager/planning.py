"""Planning: asking the manager to turn a goal into tasks.

Planning is one ability with two requests. Both are a manager turn that ends
in an ordinary proposal (ADR-0022):

``plan_sprint``
    A sprint has a goal. Propose the tasks that reach it.
``split_task``
    A task is too big to hand to one agent run. Propose smaller tasks that
    replace it.

Who confirms the proposal is the project's ``plan_approval`` policy
("Approve plans"): a person, or Foreman. Foreman confirms only a proposal
that does what was asked and nothing else; any other is left for a person.

There is no planning role and no planning step in a workflow: a task that
needs a plan before it can start is split instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..domain.errors import ForemanError
from ..domain.models import Project, Proposal
from ..domain.policy import PolicyMatrix
from .proposals import Proposals

PLAN_SPRINT = "plan_sprint"
SPLIT_TASK = "split_task"

#: Sprints tasks can still be added to, and tasks that have not started.
_PLANNABLE_SPRINTS = {"planned", "active"}
_NOT_STARTED = {"triage", "todo"}

_TASK_RULES = [
    "Each task is one coherent change that one developer agent can finish in a",
    "single run and one reviewer can check from its diff. If you would call a",
    "task large, split it now.",
    "- title: the outcome, as a short phrase.",
    "- description: what to change and where, naming files or modules you",
    "  found by reading the repository. Say what is out of scope.",
    "- acceptance_criteria: one per line, each something a reviewer can check",
    "  against the diff or a test.",
    "- waits_for: only where a task needs another's result to start. Give each",
    "  task a `ref` and name refs there.",
]


class PlanningError(ForemanError):
    """A planning request that cannot be made, with the reason."""


@dataclass(frozen=True, slots=True)
class PlanningRequest:
    """One request to the manager: what the person sees they asked, and what the manager is told."""

    kind: str
    target_id: str
    #: The line shown in the conversation as the person's message.
    says: str
    #: What the manager is told for this turn only.
    instructions: str


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def planning_request(store: Any, project: Project, plan: Mapping[str, Any]) -> PlanningRequest:
    """Build the request for ``plan``: ``{"kind": "plan_sprint", "sprint_id": ...}`` or
    ``{"kind": "split_task", "task_id": ...}``."""

    kind = _text(plan.get("kind"))
    if kind == PLAN_SPRINT:
        sprint = store.get_sprint(_text(plan.get("sprint_id")))
        if sprint is None or sprint.project_id != project.id:
            raise PlanningError("There is no such sprint in this project.")
        if sprint.status not in _PLANNABLE_SPRINTS:
            raise PlanningError(f"Sprint {sprint.title!r} is {sprint.status}; tasks cannot be added to it.")
        if not _text(sprint.goal):
            raise PlanningError(
                f"Sprint {sprint.title!r} has no goal. Give it one first: the goal is what the tasks are planned from."
            )
        existing = [task for task in store.list_tasks(sprint_id=sprint.id) if task.status != "cancelled"]
        lines = [
            f"Plan sprint {sprint.id} ({sprint.title}).",
            f"Its goal: {sprint.goal.strip()}",
            "",
            "Read the spec and the repository as far as you need to know what the goal",
            "takes. Then make ONE proposal whose operations are only `add_task` with",
            f"sprint_id {sprint.id}: the tasks that, together, reach the goal.",
            "",
            *_TASK_RULES,
            "",
        ]
        if existing:
            lines += ["Already in the sprint; do not repeat these, plan what is missing:"]
            lines += [f"- {task.id}: {task.title} ({task.status})" for task in existing]
            lines += [""]
        lines += [
            "The proposal's reason: one paragraph saying how these tasks reach the",
            "goal and what you left out. Propose nothing else in this turn.",
        ]
        return PlanningRequest(
            kind=kind,
            target_id=sprint.id,
            says=f"Plan this sprint: {sprint.title}",
            instructions="\n".join(lines),
        )

    if kind == SPLIT_TASK:
        task = store.get_task(_text(plan.get("task_id")))
        if task is None or task.project_id != project.id:
            raise PlanningError("There is no such task in this project.")
        if task.status not in _NOT_STARTED:
            raise PlanningError(
                f"Task {task.task_key or task.id} is {task.status}. Only a task that has not started can be split."
            )
        sprint = store.get_sprint(task.sprint_id) if task.sprint_id else None
        in_sprint = sprint is not None and sprint.kind != "backlog" and sprint.status in _PLANNABLE_SPRINTS
        place = (
            f"`add_task` with sprint_id {sprint.id}"
            if in_sprint
            else "`file_task` with accept true (it is in the backlog, so they go there)"
        )
        lines = [
            f"Split task {task.id} ({task.title}) into smaller tasks.",
            "",
            f"Read it with `foreman task show {task.id}` and read the code it touches.",
            "Then make ONE proposal whose operations are, in this order: two or more",
            f"{place}, which together do everything the task asks and",
            f"nothing more; then `cancel_task` with task_id {task.id}.",
            "",
            *_TASK_RULES,
            "",
            "Every acceptance criterion of the task must end up in one of the new",
            "tasks. The proposal's reason: one paragraph saying how the pieces cover",
            "the task. Propose nothing else in this turn.",
        ]
        return PlanningRequest(
            kind=kind,
            target_id=task.id,
            says=f"Split this task: {task.title}",
            instructions="\n".join(lines),
        )

    raise PlanningError("A planning request is 'plan_sprint' with a sprint_id or 'split_task' with a task_id.")


def does_only_what_was_asked(request: PlanningRequest, proposal: Proposal, store: Any) -> bool:
    """Whether a proposal is exactly a plan for the request: the tasks, and nothing else."""

    operations = proposal.operations
    if not operations:
        return False
    if request.kind == PLAN_SPRINT:
        return all(
            operation.get("kind") == "add_task" and operation.get("sprint_id") == request.target_id
            for operation in operations
        )
    *pieces, last = operations
    if last.get("kind") != "cancel_task" or last.get("task_id") != request.target_id or len(pieces) < 2:
        return False
    task = store.get_task(request.target_id)
    for operation in pieces:
        if operation.get("kind") == "add_task":
            if task is None or operation.get("sprint_id") != task.sprint_id:
                return False
        elif operation.get("kind") != "file_task":
            return False
    return True


def who_approves_plans(project: Project) -> str:
    """``"human"`` or ``"auto"``: the project's "Approve plans" decision."""

    return PolicyMatrix.from_settings(project.settings).resolve("plan_approval").value


def settle_plan(store: Any, project: Project, request: PlanningRequest, turn_id: str) -> list[str]:
    """Confirm the turn's proposals where the project lets Foreman approve plans.

    Returns the ids confirmed. A proposal that does anything but what was
    asked is left for a person, whatever the policy says.
    """

    if who_approves_plans(project) != "auto":
        return []
    confirmed: list[str] = []
    proposals = Proposals(store, via="policy", actor="foreman")
    for proposal in store.list_turn_proposals(turn_id):
        if proposal.state != "proposed" or not does_only_what_was_asked(request, proposal, store):
            continue
        if proposals.confirm(proposal.id).state == "confirmed":
            confirmed.append(proposal.id)
    return confirmed
