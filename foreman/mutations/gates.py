"""A person's decision at a human gate of a task's workflow.

The decision is recorded and the task left at the step it leads to, for
the project's engine to run (ADR-0011). Recording it is the same whether
a person decides from the CLI, the dashboard or a confirmed proposal, or
``foreman approve`` continues the task in the same process; so the record
is written here, and the orchestrator calls it too.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from ..definitions.gate_steps import HUMAN_GATE_ROLE, blocked_kind, resolve_gate_steps
from ..definitions.layers import project_definitions
from ..definitions.workflows import WorkflowDefinition, WorkflowStep
from ..domain.models import HumanGateDecision, MergeWaiver, Project, Task, utc_now_text
from ..history.records import RunRecords, new_id
from ..notifications.delivery import NotificationDispatcher
from ..repo.git import head_sha
from ..store import ForemanStore
from .base import MutationBase, MutationError

#: The evidence checks a person may waive for one merge.
MERGE_WAIVER_TYPES: frozenset[str] = frozenset(
    {"missing_acceptance_criteria", "incomplete_criteria", "no_code_delta", "docs_only_impl_task"}
)

#: Gate decisions, as the workflow names them.
GATE_OUTCOMES: tuple[str, ...] = ("approve", "deny")


@dataclass(frozen=True)
class GateDecision:
    """A gate decision recorded, and the step the task now waits at."""

    task: Task
    outcome: str
    next_step: str | None
    deferred: bool


@dataclass(frozen=True)
class GateStop:
    """A task paused at a human gate, and the step a decision leads to."""

    task: Task
    project: Project
    workflow: WorkflowDefinition
    paused_step: str
    next_step: WorkflowStep


@dataclass(frozen=True)
class GateRecord:
    """A gate decision as written: the task after it, and what it carries on."""

    task: Task
    carried_output: str | None


def find_gate_stop(
    store: ForemanStore,
    task_id: str,
    outcome: str,
    workflow_for: Callable[[Project], WorkflowDefinition],
) -> GateStop:
    """Check a task waits at a human gate that has a way out for ``outcome``.

    ``workflow_for`` loads the project's workflow: the engine passes the one
    it has loaded, a person's change loads the project's definitions.
    """

    if outcome not in GATE_OUTCOMES:
        raise MutationError(f"Unsupported human-gate outcome {outcome!r}.")
    task = store.get_task(task_id)
    if task is None:
        raise MutationError(f"Unknown task {task_id!r}.")
    if task.status != "blocked" or not task.workflow_current_step:
        raise MutationError(f"Task {task_id!r} is not paused at a human gate.")
    project = store.get_project(task.project_id)
    if project is None:
        raise MutationError(
            f"Task {task_id!r} references unknown project {task.project_id!r}."
        )
    workflow = workflow_for(project)
    paused_step = workflow.get_step(task.workflow_current_step)
    if paused_step is None or paused_step.role != HUMAN_GATE_ROLE:
        raise MutationError(f"Task {task_id!r} is not paused on a resumable human-gate step.")
    transition = workflow.find_transition(paused_step.id, outcome)
    if transition is None:
        raise MutationError(
            f"Workflow {workflow.id!r} has no `{outcome}` transition from {paused_step.id!r}."
        )
    next_step = workflow.get_step(transition.to_step)
    if next_step is None:
        raise MutationError(f"Workflow {workflow.id!r} is missing step {transition.to_step!r}.")
    return GateStop(
        task=task,
        project=project,
        workflow=workflow,
        paused_step=paused_step.id,
        next_step=next_step,
    )


def record_gate_decision(
    store: ForemanStore,
    records: RunRecords,
    stop: GateStop,
    *,
    outcome: str,
    note: str | None,
    deferred: bool,
    save: Callable[[Task], None],
) -> GateRecord:
    """Write a gate decision: its run, its events, its row, and the task after it.

    ``deferred`` leaves the task at the step the decision leads to, for the
    project's engine to run; otherwise the caller (the engine itself) runs
    that step now. ``save`` writes the task the way the caller writes tasks.
    One task write: a crash between "decision recorded" and "next step
    recorded" must not leave a task that restarts from its entry step.
    """

    task = stop.task
    carried_output = task.workflow_carried_output
    if outcome == "deny" and note:
        carried_output = note
    detail = note or ("Approved by human." if outcome == "approve" else "Denied by human.")
    run = records.create_system_run(
        task,
        workflow_step=stop.paused_step,
        outcome=outcome,
        detail=detail,
        role_id=HUMAN_GATE_ROLE,
        agent_backend="human",
    )
    records.emit_event(
        run,
        "workflow.transition",
        {
            "from_step": stop.paused_step,
            "to_step": stop.next_step.id,
            "trigger": f"completion:{outcome}",
        },
    )
    resumed = {
        "step": stop.paused_step,
        "decision": outcome,
        "next_step": stop.next_step.id,
        "deferred": deferred,
    }
    if note:
        resumed["note"] = note
    records.emit_event(run, "workflow.resumed", resumed)
    store.save_human_gate_decision(
        HumanGateDecision(
            id=new_id("hg"),
            task_id=task.id,
            project_id=stop.project.id,
            workflow_step=stop.paused_step,
            decision=outcome,
            note=note,
            decided_by="human",
            decided_at=utc_now_text(),
            run_id=run.id,
        )
    )
    task.status = "in_progress"
    task.blocked_reason = None
    task.workflow_current_step = stop.next_step.id if deferred else None
    task.workflow_carried_output = carried_output if deferred else None
    save(task)
    return GateRecord(task=task, carried_output=carried_output)


class GateMutations(MutationBase):
    """Gate decisions, and sending a waiting task back with guidance."""

    def decide_gate(self, task: Task, outcome: str, note: str | None = None) -> GateDecision:
        """Approve or deny a task waiting at a human gate of its workflow.

        The decision is recorded and the task left at the step it leads to,
        for the project's engine to run (ADR-0011); nothing runs here.
        """

        if outcome not in GATE_OUTCOMES:
            raise MutationError(f"Unknown gate decision: {outcome}.")
        clean_note = (note or "").strip() or None
        stop = find_gate_stop(self.store, task.id, outcome, self._project_workflow)
        record_gate_decision(
            self.store,
            RunRecords(self.store, NotificationDispatcher(self.store)),
            stop,
            outcome=outcome,
            note=clean_note,
            deferred=True,
            save=self._save_engine_state,
        )
        decided = self.store.get_task(task.id) or task
        if self.proposal_id:
            # The gate's own records (workflow.resumed, the decision row) have
            # no place for the proposal; this event names it.
            self._audit(
                decided,
                "human.gate_decided",
                step="gate",
                decision=outcome,
                note=clean_note,
                next_step=stop.next_step.id,
            )
        return GateDecision(task=decided, outcome=outcome, next_step=stop.next_step.id, deferred=True)

    def _project_workflow(self, project: Project) -> WorkflowDefinition:
        """The project's workflow, its own over the shipped one (ADR-0024)."""

        workflow = project_definitions(self.store, project.id).workflows.get(project.workflow_id)
        if workflow is None:
            raise MutationError(
                f"Unknown workflow {project.workflow_id!r} for project {project.id!r}."
            )
        return workflow

    def _save_engine_state(self, task: Task) -> None:
        """Write the task's workflow state as the engine would (``TaskWrites``)."""

        written = self.store.update_task_engine_state(task)
        if written is None:
            self.store.save_task(task)
        elif written is False:
            raise MutationError(f"Task {task.id} was cancelled; its gate cannot be decided.")

    def send_back(self, task: Task, guidance: str) -> Task:
        """Send a task that waits for a person back to work, with guidance.

        At a human gate it is the workflow's denial, carrying the guidance to
        the step a refusal leads to. A blocked task goes back to the queue
        (``unblock_task``) and the guidance is recorded for its next step.
        """

        clean = (guidance or "").strip()
        if not clean:
            raise MutationError("Say what should change: guidance is required to send a task back.")
        if task.status != "blocked":
            raise MutationError(
                f"Task {task.id} is {task.status}, not waiting for a person; only a task "
                "waiting at a gate or blocked can be sent back."
            )
        project = self.store.get_project(task.project_id)
        gates = resolve_gate_steps(self.store, project)
        if blocked_kind(task, gates) == "gate":
            return self.decide_gate(task, "deny", clean).task
        unblocked = self.unblock_task(task)
        self.record_guidance(unblocked, clean)
        return unblocked

    def waive_merge(
        self,
        task: Task,
        *,
        waiver_type: str,
        reason: str,
        approved_by: str | None = None,
    ) -> MergeWaiver:
        """Let a task merge past one evidence check, at its branch's current commit.

        The waiver names the branch and the commits it was given at, so a
        later commit is not covered by it.
        """

        if waiver_type not in MERGE_WAIVER_TYPES:
            raise MutationError(
                f"Invalid waiver type {waiver_type!r}. "
                f"Must be one of: {', '.join(sorted(MERGE_WAIVER_TYPES))}"
            )
        project = self.store.get_project(task.project_id)
        if project is None:
            raise MutationError(f"Project not found: {task.project_id}")
        branch_name = task.branch_name or "unknown"
        try:
            branch_sha = head_sha(project.repo_path, f"refs/heads/{branch_name}") or ""
            base_sha = head_sha(project.repo_path, f"refs/heads/{project.default_branch}") or ""
        except Exception as exc:  # noqa: BLE001 - any git failure refuses the waiver
            raise MutationError(f"Failed to get branch SHA: {exc}") from exc
        waiver = MergeWaiver(
            id=f"waiver-{uuid4().hex[:12]}",
            task_id=task.id,
            project_id=task.project_id,
            waiver_type=waiver_type,
            reason=reason,
            approved_by=approved_by or "human",
            approved_at=self._now().isoformat(),
            branch_name=branch_name,
            head_sha=branch_sha,
            base_sha=base_sha,
            expires_at=None,
            revoked_at=None,
        )
        self.store.save_merge_waiver(waiver)
        return waiver
