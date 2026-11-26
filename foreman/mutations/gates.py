"""A person's decision at a human gate of a task's workflow.

The decision is recorded and the task left at the step it leads to, for
the project's engine to run (ADR-0011). Recording it is the same whether
a person decides from the CLI, the dashboard or a confirmed proposal, or
``foreman approve`` continues the task in the same process; so the record
is written here, and the orchestrator calls it too.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from uuid import uuid4

from ..definitions.gate_steps import (
    HUMAN_GATE_ROLE,
    blocked_kind,
    resolve_gate_steps,
    steps_into,
)
from ..definitions.layers import project_definitions
from ..definitions.workflows import WorkflowDefinition, WorkflowStep
from ..domain.gate_version import (
    MERGE_APPROVAL,
    PLAN_APPROVAL,
    GateVersion,
    malformed_version,
    names_current,
    plan_fingerprint,
)
from ..domain.models import HumanGateDecision, MergeWaiver, Project, Run, Task, utc_now_text
from ..history.records import RunRecords, new_id
from ..notifications.delivery import NotificationDispatcher
from ..repo.git import head_sha
from ..store import ForemanStore
from .base import MutationBase, MutationError

#: The evidence checks a person may waive for one merge.
MERGE_WAIVER_TYPES: frozenset[str] = frozenset(
    {"missing_acceptance_criteria", "no_code_delta", "docs_only_impl_task"}
)

#: Gate decisions, as the workflow names them.
GATE_OUTCOMES: tuple[str, ...] = ("approve", "deny")


class GateVersionChanged(MutationError):
    """The version a decision names is no longer the current one."""

    def __init__(self, message: str, current: GateVersion) -> None:
        super().__init__(message)
        self.current = current


class GateVersionInvalid(MutationError):
    """The version a decision names cannot name a version of this gate at all.

    Too short, not a commit or a fingerprint, or given at a gate that has
    nothing to name: a mistake in the request, not a change under it.
    """


def current_gate_version(
    store: ForemanStore,
    project: Project,
    task: Task,
    policy: str | None,
    *,
    plan_steps: Collection[str] | None = None,
) -> GateVersion:
    """What is in front of a person at a gate of ``policy`` for ``task``, now.

    A merge approval is of the task branch's head and the default branch's
    head; a plan approval is of the task's description and criteria and the
    run whose plan it is: the last agent run of a step the gate is reached
    from (``plan_steps``; any agent step when the workflow is not known). A
    gate with another policy has no version.
    """

    if policy == MERGE_APPROVAL:
        branch = f"refs/heads/{task.branch_name}" if task.branch_name else None
        try:
            branch_sha = head_sha(project.repo_path, branch) if branch else None
            base_sha = head_sha(project.repo_path, f"refs/heads/{project.default_branch}")
        except Exception:  # noqa: BLE001 - no repository: the decision has no commit to name
            branch_sha = base_sha = None
        return GateVersion(kind=policy, branch_sha=branch_sha, base_sha=base_sha)
    if policy == PLAN_APPROVAL:
        run = plan_run(store.list_runs(task_id=task.id), plan_steps)
        run_id = run.id if run is not None else None
        return GateVersion(
            kind=policy,
            fingerprint=plan_fingerprint(task.description, task.acceptance_criteria, run_id),
            plan_run_id=run_id,
        )
    return GateVersion()


def plan_run(runs: Sequence[Run], plan_steps: Collection[str] | None) -> Run | None:
    """The run whose plan a plan approval is of: the last agent run of a step before the gate.

    A person's decision, the engine's own records and built-in steps write
    no plan, so they are never it. ``plan_steps`` are the steps the gate is
    reached from; ``None`` (the workflow is not known) takes any agent step.
    """

    for run in reversed(runs):
        if run.role_id.startswith("_builtin:") or run.agent_backend in {"human", "builtin"}:
            continue
        if plan_steps is None or run.workflow_step in plan_steps:
            return run
    return None


def gate_version_now(store: ForemanStore, project: Project, task: Task) -> GateVersion:
    """The version at the gate ``task`` waits at, its workflow read from the project.

    For a caller that has no workflow at hand (a proposal); a task not at a
    human gate, or a workflow that will not load, has no version.
    """

    if task.status != "blocked" or not task.workflow_current_step:
        return GateVersion()
    try:
        workflow = project_definitions(store, project.id).workflows.get(project.workflow_id)
    except Exception:  # noqa: BLE001 - a broken definition: nothing to name
        return GateVersion()
    step = workflow.get_step(task.workflow_current_step) if workflow is not None else None
    if workflow is None or step is None or step.role != HUMAN_GATE_ROLE:
        return GateVersion()
    return current_gate_version(
        store, project, task, step.policy, plan_steps=steps_into(workflow, step.id)
    )


def _changed_message(seen: str, current: GateVersion) -> str:
    if current.kind == MERGE_APPROVAL:
        return (
            f"The branch moved: you saw {seen[:7]}, it is now at {current.short}. "
            "Review the new version and decide again."
        )
    return (
        f"The plan changed: you saw {seen[:7]}, it is now {current.short}. "
        "Review the new version and decide again."
    )


@dataclass(frozen=True)
class GateDecision:
    """A gate decision recorded, and the step the task now waits at."""

    task: Task
    outcome: str
    next_step: str | None
    deferred: bool
    version: GateVersion = GateVersion()
    version_named: bool = False


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
    version: GateVersion = GateVersion()
    version_named: bool = False


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
    seen_version: str | None = None,
) -> GateRecord:
    """Write a gate decision: its run, its events, its row, and the task after it.

    ``deferred`` leaves the task at the step the decision leads to, for the
    project's engine to run; otherwise the caller (the engine itself) runs
    that step now. ``save`` writes the task the way the caller writes tasks.
    One task write: a crash between "decision recorded" and "next step
    recorded" must not leave a task that restarts from its entry step.
    """

    task = stop.task
    gate_step = stop.workflow.get_step(stop.paused_step)
    version = current_gate_version(
        store,
        stop.project,
        task,
        gate_step.policy if gate_step else None,
        plan_steps=steps_into(stop.workflow, stop.paused_step),
    )
    named = False
    if seen_version is not None and seen_version.strip():
        # A version that cannot name one of this gate is a mistake in the
        # request, refused whatever the decision.
        problem = malformed_version(seen_version, version)
        if problem is not None:
            raise GateVersionInvalid(problem)
        # The version the person saw. An approval of one that has since
        # changed is refused; a send-back of it is not, it needs no version.
        if not names_current(seen_version, version.token):
            if outcome == "approve":
                raise GateVersionChanged(
                    _changed_message(seen_version.strip(), version), version
                )
        else:
            named = True
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
    if version.kind:
        resumed["version"] = {**version.to_dict(), "named": named}
    records.emit_event(run, "workflow.resumed", resumed)
    if version.branch_sha:
        # The commit it decided on is the run's commit: the Activity line
        # reads "Approved at abc1234" from it.
        run.commit_sha = version.branch_sha
        store.save_run(run)
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
            branch_sha=version.branch_sha,
            base_sha=version.base_sha,
            plan_fingerprint=version.fingerprint,
            plan_run_id=version.plan_run_id,
            version_named=named,
        )
    )
    task.status = "in_progress"
    task.blocked_reason = None
    task.workflow_current_step = stop.next_step.id if deferred else None
    task.workflow_carried_output = carried_output if deferred else None
    save(task)
    return GateRecord(
        task=task, carried_output=carried_output, version=version, version_named=named
    )


class GateMutations(MutationBase):
    """Gate decisions, and sending a waiting task back with guidance."""

    def decide_gate(
        self,
        task: Task,
        outcome: str,
        note: str | None = None,
        *,
        seen_version: str | None = None,
    ) -> GateDecision:
        """Approve or deny a task waiting at a human gate of its workflow.

        The decision is recorded and the task left at the step it leads to,
        for the project's engine to run (ADR-0011); nothing runs here.
        """

        if outcome not in GATE_OUTCOMES:
            raise MutationError(f"Unknown gate decision: {outcome}.")
        clean_note = (note or "").strip() or None
        stop = find_gate_stop(self.store, task.id, outcome, self._project_workflow)
        recorded = record_gate_decision(
            self.store,
            RunRecords(self.store, NotificationDispatcher(self.store)),
            stop,
            outcome=outcome,
            note=clean_note,
            deferred=True,
            save=self._save_engine_state,
            seen_version=seen_version,
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
        return GateDecision(
            task=decided,
            outcome=outcome,
            next_step=stop.next_step.id,
            deferred=True,
            version=recorded.version,
            version_named=recorded.version_named,
        )

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
                f"Task {task.id} is {task.status}, not waiting for a user; only a task "
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
