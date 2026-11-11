"""Task orchestration for Foreman workflow execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .builtins import BuiltinExecutor
from .context import (
    build_project_context,
)
from .engine.errors import (
    LeaseLostError,
    OrchestratorError,
    QuotaPauseError,
    TaskExecutionError,
)
from .engine.agent_step import DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS, AgentStepRunner
from .engine.branch_sync import (
    context_mirror_dirs,
)
from .engine.evidence import EvidenceBuilder
from .engine.leasing import TASK_LEASE_HEARTBEAT_SECONDS, TaskLeases
from .engine.limits import (
    resolve_project_settings,
)
from .engine.prompts import PromptBuilder
from .engine.records import RunRecords, new_id
from .engine.task_worktrees import TaskWorktrees
from .engine.workflow_runner import WorkflowRunner
from .engine.retention import Retention
from .engine.sprints import SprintFlow
from .engine.task_writes import TaskWrites
from .engine.recovery import Recovery
from .engine.selection import TaskSelector
from .engine.signals import SignalHandler
from .engine.results import (
    AgentExecutor,
    HumanGateResumeResult,
    ProjectRunResult,
    quota_run_result,
)
from .errors import EngineCommandInterrupt
from .logs import get_logger
from .models import CompletionEvidence, Event, HumanGateDecision, Project, Task, utc_now_text
from .notifications import NotificationDispatcher
from .outcomes import APPROVE, DENY
from .runner import ClaudeCodeRunner, CodexRunner
from .runner.base import AgentRunner as NativeAgentRunner
from .runner.process import EngineShutdown
from .roles import RoleDefinition, default_roles_dir, load_roles
from .store import ForemanStore
from .workflows import WorkflowDefinition, default_workflows_dir, load_workflows

_LOGGER = get_logger("orchestrator")

_BRANCH_PREFIXES = {
    "feature": "feat",
    "fix": "fix",
    "refactor": "refactor",
    "docs": "docs",
    "spike": "spike",
    "chore": "chore",
}


class ForemanOrchestrator:
    """Drive persisted tasks through declarative workflows."""

    # Minimum interval (seconds) between task-lease renewals while a native
    # runner step is streaming. The default 30s is well under the 5-minute lease
    # duration so a long Claude/Codex stream keeps the lease alive.
    _DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS = DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS

    # Maximum heartbeat age (seconds) below which a lease is still considered
    # alive for active-run recovery. If the lease's heartbeat is older than
    # this window, recovery treats the holder as gone even if the lease is
    # technically still within its ``expires_at`` window.
    _LEASE_LIVENESS_THRESHOLD_SECONDS = 60.0
    # Well inside both the 300-second lease and the 60-second liveness window
    # above; see foreman/task_lease.py.
    _TASK_LEASE_HEARTBEAT_SECONDS = TASK_LEASE_HEARTBEAT_SECONDS

    def __init__(
        self,
        store: ForemanStore,
        *,
        roles: Mapping[str, RoleDefinition] | None = None,
        workflows: Mapping[str, WorkflowDefinition] | None = None,
        agent_executor: AgentExecutor | None = None,
        agent_runners: Mapping[str, NativeAgentRunner] | None = None,
        builtin_executor: BuiltinExecutor | None = None,
        runner_sleep: Callable[[float], None] | None = None,
        utc_now: Callable[[], datetime] | None = None,
        holder_id: str | None = None,
        native_step_heartbeat_seconds: float | None = None,
        command_poll: Callable[[str], None] | None = None,
        notifier: NotificationDispatcher | None = None,
    ) -> None:
        loaded_roles = dict(roles) if roles is not None else load_roles(default_roles_dir())
        loaded_workflows = (
            dict(workflows)
            if workflows is not None
            else load_workflows(
                default_workflows_dir(),
                available_role_ids=set(loaded_roles),
                role_outcomes={
                    role_id: role.completion.outcomes
                    for role_id, role in loaded_roles.items()
                },
            )
        )
        self.store = store
        self.roles = loaded_roles
        self.evidence = EvidenceBuilder(self.store, self.roles)
        self.workflows = loaded_workflows
        self.agent_executor = agent_executor
        self.agent_runners = (
            dict(agent_runners)
            if agent_runners is not None
            else {
                "claude_code": ClaudeCodeRunner(),
                "codex": CodexRunner(),
            }
        )
        self.builtin_executor = builtin_executor or BuiltinExecutor()
        #: Offered every persisted event; queues the announceable ones as
        #: deliveries. Injectable so a test can watch what the engine chose to
        #: announce without a transport, and so a caller that has no business
        #: notifying anyone can pass one that does nothing.
        self.notifier = notifier if notifier is not None else NotificationDispatcher(store)
        self.records = RunRecords(store, self.notifier)
        self.tasks = TaskWrites(store)
        self.runner_sleep = runner_sleep
        self.utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self.retention = Retention(store, self.records, self.utc_now)
        self.sprints = SprintFlow(store, self.records, self.utc_now)
        self.holder_id = holder_id or str(uuid4())
        if native_step_heartbeat_seconds is not None and native_step_heartbeat_seconds < 0:
            native_step_heartbeat_seconds = 0.0
        self._native_step_heartbeat_seconds = (
            native_step_heartbeat_seconds
            if native_step_heartbeat_seconds is not None
            else self._DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS
        )
        self.leases = TaskLeases(
            store, self.holder_id, heartbeat_seconds=self._TASK_LEASE_HEARTBEAT_SECONDS
        )
        self.agent_steps = AgentStepRunner(
            agent_executor=self.agent_executor,
            agent_runners=self.agent_runners,
            leases=self.leases,
            records=self.records,
            runner_sleep=self.runner_sleep,
            utc_now=self.utc_now,
            heartbeat_seconds=self._native_step_heartbeat_seconds,
            poll_commands=self._poll_commands,
        )
        self.recovery = Recovery(
            store,
            records=self.records,
            leases=self.leases,
            tasks=self.tasks,
            utc_now=self.utc_now,
        )
        self.selector = TaskSelector(
            store,
            leases=self.leases,
            tasks=self.tasks,
            block_task_for_error=self.block_task_for_error,
        )
        self.signals = SignalHandler(
            store,
            roles=self.roles,
            records=self.records,
            leases=self.leases,
            tasks=self.tasks,
        )
        self.task_worktrees = TaskWorktrees(store, records=self.records, tasks=self.tasks)
        self.prompts = PromptBuilder(
            store,
            evidence=self.evidence,
            tasks=self.tasks,
            build_evidence=lambda task, project: self.build_completion_evidence(task, project),
        )
        self.runner = WorkflowRunner(
            store,
            roles=self.roles,
            records=self.records,
            leases=self.leases,
            tasks=self.tasks,
            task_worktrees=self.task_worktrees,
            prompts=self.prompts,
            agent_steps=self.agent_steps,
            signals=self.signals,
            evidence=self.evidence,
            builtin_executor=self.builtin_executor,
            poll_commands=self._poll_commands,
            build_evidence=lambda task, project: self.build_completion_evidence(task, project),
        )
        #: Called with the running task id before every workflow step and on
        #: every silent-agent tick. The resident engine supplies it so an
        #: operator's `pause` or `stop_task` reaches an agent that may run for
        #: an hour. It returns normally to continue and raises
        #: ``EngineCommandInterrupt`` to stop the step. A one-shot ``foreman
        #: run`` leaves it None and behaves exactly as before.
        self.command_poll = command_poll

    def close(self) -> None:
        """Stop the background work this orchestrator started."""

        self.leases.close()

    def run_workflow_from_step(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
        *,
        step: str,
        carried_output: str | None,
    ) -> Task:
        """Run a task from one workflow step (see ``engine.workflow_runner``)."""

        return self.runner.run_from_step(
            project, workflow, task, step=step, carried_output=carried_output
        )

    def select_next_task(self, project: Project) -> Task | None:
        """Pick and lease the next runnable task (see ``engine.selection``)."""

        return self.selector.select_next_task(project)

    def recover_orphaned_tasks(self, project_id: str) -> None:
        """Reset tasks an earlier engine left mid-work (see ``engine.recovery``)."""

        self.recovery.recover_orphaned_tasks(project_id)

    def build_completion_evidence(
        self, task: Task, project: Project
    ) -> CompletionEvidence | None:
        """Build completion evidence for one task (see ``engine.evidence``)."""

        return self.evidence.build(task, project)

    def _poll_commands(self, task_id: str) -> None:
        """Give the resident engine a chance to interrupt this task.

        Raises ``EngineCommandInterrupt`` when the engine wants the step
        stopped. Any *other* exception from the callback is deliberately not
        caught: a command poll that cannot read the database is a broken
        control channel, and hiding it would leave an operator's `pause`
        silently ignored.
        """

        if self.command_poll is not None:
            self.command_poll(task_id)

    def run_project(
        self,
        project_id: str,
        *,
        task_id: str | None = None,
        maintenance: bool = True,
    ) -> ProjectRunResult:
        """Run one project's active workflow until no runnable task remains.

        ``maintenance`` controls the once-per-startup housekeeping (retention
        pruning and crash recovery). A resident engine passes ``False`` on an
        idle wake: nothing has executed since the last pass, so re-pruning and
        re-scanning for orphans on every wake would be pure load.
        """

        project = self.store.get_project(project_id)
        if project is None:
            raise OrchestratorError(f"Unknown project {project_id!r}.")
        settings = resolve_project_settings(project)
        workflow = self._load_workflow_for_project(project)
        self.task_worktrees.preflight(project)
        if maintenance:
            self.retention.prune_old_history(project, settings=settings)
            self.recovery.recover_orphaned_tasks(project.id)

        executed_task_ids: list[str] = []
        blocked_task_ids: list[str] = []
        if task_id is not None:
            task = self.store.get_task(task_id)
            if task is None or task.project_id != project.id:
                raise OrchestratorError(
                    f"Task {task_id!r} does not belong to project {project.id!r}."
                )
            # Acquire the lease before running; skip if task is already leased
            # by another orchestrator.
            if self.leases.acquire(task, project) is None:
                raise OrchestratorError(
                    f"Task {task_id!r} is already leased by another orchestrator."
                )
            try:
                completed = self._run_task_isolated(project, workflow, task)
            except QuotaPauseError as exc:
                return quota_run_result(project, exc, executed_task_ids, blocked_task_ids)
            executed_task_ids.append(completed.id)
            if completed.status == "blocked":
                blocked_task_ids.append(completed.id)
            return ProjectRunResult(
                project_id=project.id,
                executed_task_ids=tuple(executed_task_ids),
                blocked_task_ids=tuple(blocked_task_ids),
                stop_reason="task_complete",
            )

        self.sprints.activate_first_planned(project.id)
        stop_reason = "idle"
        while True:
            task = self.selector.select_next_task(project)
            if task is not None:
                try:
                    completed = self._run_task_isolated(project, workflow, task)
                except QuotaPauseError as exc:
                    return quota_run_result(
                        project, exc, executed_task_ids, blocked_task_ids
                    )
                executed_task_ids.append(completed.id)
                if completed.status == "blocked":
                    blocked_task_ids.append(completed.id)
                continue

            # No runnable task — check sprint state.
            sprint = self.store.get_active_sprint(project.id)
            if sprint is not None and self.sprints.fully_resolved(sprint):
                result = self.sprints.advance(project, sprint)
                if result is None:
                    # Autonomous mode: next sprint now active — keep looping.
                    continue
                stop_reason = result
            else:
                remaining = (
                    self.store.list_tasks(sprint_id=sprint.id)
                    if sprint is not None
                    else []
                )
                if any(t.status == "blocked" for t in remaining):
                    stop_reason = "blocked"
                elif any(t.status in {"todo", "in_progress"} for t in remaining):
                    stop_reason = "waiting"
                else:
                    stop_reason = "idle"
            break

        return ProjectRunResult(
            project_id=project.id,
            executed_task_ids=tuple(executed_task_ids),
            blocked_task_ids=tuple(blocked_task_ids),
            stop_reason=stop_reason,
        )

    def _run_task_isolated(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
    ) -> Task:
        """Run one task, tagging any failure with the task it belongs to.

        Shutdown and lease loss are engine-level events and pass through
        untouched. Everything else — ``OrchestratorError``, ``GitError``, an
        unexpected exception — is re-raised as :class:`TaskExecutionError` so
        the caller knows which task to block instead of guessing.
        """

        try:
            return self.run_task(project, workflow, task)
        except (
            EngineCommandInterrupt,
            EngineShutdown,
            KeyboardInterrupt,
            LeaseLostError,
            QuotaPauseError,
            TaskExecutionError,
        ):
            raise
        except Exception as exc:
            raise TaskExecutionError(task.id, exc) from exc

    def block_task_for_error(
        self,
        task_id: str,
        reason: str,
        *,
        attention_trigger: str = "task_blocked",
    ) -> Task | None:
        """Block one task after an engine-level failure and raise attention.

        Used by the resident engine to isolate a failed task: the task is
        parked as ``blocked`` with the failure text, a system run records what
        happened, and ``engine.attention_needed`` reaches the supervision
        digest through the same path a workflow block takes. Returns the task,
        or None when it no longer exists.
        """

        task = self.store.get_task(task_id)
        if task is None:
            return None

        project = self.store.get_project(task.project_id)
        if project is not None:
            self.leases.release(task, project)

        workflow_step = task.workflow_current_step or "orchestrator"
        if task.status not in {"done", "cancelled"}:
            task.status = "blocked"
            task.blocked_reason = reason
            self.tasks.save(task)
        self.records.create_system_run(
            task,
            workflow_step=workflow_step,
            outcome="blocked",
            detail=reason,
            attention_trigger=attention_trigger,
        )
        return task

    def release_task(self, task_id: str) -> None:
        """Drop this engine's lease on one task without changing its status.

        Used when a command stops work on a task that must stay exactly as it
        is — a paused engine leaves the task ``in_progress`` and resumable, but
        it must not keep holding the lease while it sits idle, or nothing else
        could ever pick the task up.
        """

        task = self.store.get_task(task_id)
        if task is None:
            return
        project = self.store.get_project(task.project_id)
        if project is not None:
            self.leases.release(task, project)

    def stop_task(self, task_id: str, *, reason: str) -> Task | None:
        """Park one task as ``blocked`` at an operator's request.

        Distinct from :meth:`block_task_for_error`: a requested stop is not an
        anomaly, so it records no system run of its own and raises no attention
        turn — the caller records why it stopped the task. ``blocked`` is
        reused rather than inventing a status because a stopped task needs
        exactly what ``blocked`` already means: not runnable until a human or
        the manager says otherwise. Returns the task, or None if it is gone.
        """

        task = self.store.get_task(task_id)
        if task is None:
            return None
        project = self.store.get_project(task.project_id)
        if project is not None:
            self.leases.release(task, project)
        if task.status in {"done", "cancelled"}:
            return task
        task.status = "blocked"
        task.blocked_reason = reason
        self.tasks.save(task)
        return task

    def record_engine_event(
        self,
        *,
        project_id: str,
        event_type: str,
        payload: dict[str, Any],
        task_id: str | None = None,
        detail: str = "",
        outcome: str = "success",
        workflow_step: str = "orchestrator",
    ) -> Event | None:
        """Record one engine-level event on a system run.

        Anchors on ``task_id`` when the event is about a task and on the
        project's system task otherwise, because an event row needs a run and a
        run needs a task. Returns None when the project has no task at all to
        anchor to — a real situation on an empty project, and not worth failing
        a command over.
        """

        task = self.store.get_task(task_id) if task_id else None
        if task is None:
            task = self.records.select_project_system_task(project_id)
        if task is None:
            return None
        run = self.records.create_system_run(
            task,
            workflow_step=task.workflow_current_step or workflow_step,
            outcome=outcome,
            detail=detail,
        )
        return self.records.emit_event(run, event_type, payload)

    def run_task(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
    ) -> Task:
        """Run one task from the workflow entry step, heartbeating its lease throughout."""

        token = self.leases.token_for(task.id)
        if token is not None:
            self.leases.start_heartbeat(task, project, token)
        try:
            return self._run_leased_task(project, workflow, task)
        finally:
            self.leases.stop_heartbeat(task.id)

    def _run_leased_task(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
    ) -> Task:
        """Run one task from the workflow entry step."""

        current_task = self.store.get_task(task.id)
        if current_task is None:
            raise OrchestratorError(f"Unknown task {task.id!r}.")
        if current_task.status in {"done", "cancelled"}:
            return current_task

        # Verify this orchestrator holds a valid lease on the task.
        active_lease = self.store.get_active_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=current_task.id,
        )
        if active_lease is None or active_lease.holder_id != self.holder_id:
            raise OrchestratorError(
                f"Task {task.id!r} is not leased by this orchestrator. "
                f"Use select_next_task() to acquire a task lease first."
            )

        active_runs = self.store.list_runs(task_id=current_task.id, status="running")
        if active_runs:
            recoverable_runs = [
                run for run in active_runs if self.recovery.run_is_stale(project, run)
            ]
            if recoverable_runs:
                self.recovery.recover_stale_running_runs(project, current_task, recoverable_runs)
                current_task = self.store.get_task(task.id) or current_task
                active_runs = self.store.list_runs(task_id=current_task.id, status="running")
            if active_runs:
                raise OrchestratorError(
                    f"Task {task.id!r} already has an active run and cannot be started again yet."
                )
        resume_step = workflow.entry_step
        resume_carried_output: str | None = None
        is_resuming = current_task.workflow_current_step is not None

        if current_task.status == "blocked":
            if current_task.workflow_current_step:
                paused_step = workflow.get_step(current_task.workflow_current_step)
                if paused_step is not None and paused_step.role == "_builtin:human_gate":
                    raise OrchestratorError(
                        f"Task {task.id!r} is paused at a human gate and must be resumed with "
                        f"`foreman approve` or `foreman deny`."
                    )
            raise OrchestratorError(
                f"Task {task.id!r} is blocked and cannot be run until it is resumed or unblocked."
            )

        if is_resuming:
            persisted_step = workflow.get_step(current_task.workflow_current_step or "")
            if persisted_step is None:
                raise OrchestratorError(
                    f"Task {task.id!r} cannot resume from unknown step "
                    f"{current_task.workflow_current_step!r}."
                )
            resume_step = persisted_step.id
            resume_carried_output = current_task.workflow_carried_output

        # Every task gets its own branch and worktree from the engine, in both
        # selection modes (ADR-0012). In autonomous mode the agent chooses what
        # to work on, not where: without a worktree it would run in the
        # operator's checkout and commit to whatever is checked out there.
        current_task.branch_name = current_task.branch_name or generate_branch_name(
            current_task
        )
        self.task_worktrees.ensure(project, current_task)

        current_task.status = "in_progress"
        current_task.blocked_reason = None
        current_task.workflow_current_step = None
        current_task.workflow_carried_output = None
        if not is_resuming:
            current_task.step_visit_counts = {}
        current_task.started_at = current_task.started_at or utc_now_text()
        self.tasks.save(current_task)

        # No try/finally around the workflow: the engine never changes what is
        # checked out in the operator's repository, so there is no branch to
        # restore when a task ends, pauses, or fails.
        self.runner.run_from_step(
            project,
            workflow,
            current_task,
            step=resume_step,
            carried_output=resume_carried_output,
        )
        refreshed = self.store.get_task(current_task.id)
        if refreshed is None:
            raise OrchestratorError(f"Task {current_task.id!r} disappeared during execution.")
        latest_run = self.store.get_latest_run(refreshed.id)
        if latest_run is not None:
            self.runner.write_runtime_context(
                latest_run,
                project,
                context_projection=build_project_context(
                    self.store,
                    project,
                    current_task=refreshed,
                    carried_output=refreshed.workflow_carried_output,
                    mirror_dirs=context_mirror_dirs(project, refreshed),
                ),
            )
        return refreshed

    def resume_human_gate(
        self,
        task_id: str,
        *,
        outcome: str,
        note: str | None = None,
        defer: bool = False,
    ) -> HumanGateResumeResult:
        """Apply one human-gate decision and continue execution when possible.

        With ``defer`` the decision is recorded and the task is left
        ``in_progress`` at the step the decision leads to, for the project's
        engine to continue. That is what every caller outside an engine must
        use: the CLI and the dashboard decide, the engine (which holds the
        project lock and the task lease) executes. ADR-0011.
        """

        if outcome not in {APPROVE, DENY}:
            raise OrchestratorError(f"Unsupported human-gate outcome {outcome!r}.")

        current_task = self.store.get_task(task_id)
        if current_task is None:
            raise OrchestratorError(f"Unknown task {task_id!r}.")
        if current_task.status != "blocked" or not current_task.workflow_current_step:
            raise OrchestratorError(
                f"Task {task_id!r} is not paused at a human gate."
            )

        project = self.store.get_project(current_task.project_id)
        if project is None:
            raise OrchestratorError(
                f"Task {task_id!r} references unknown project {current_task.project_id!r}."
            )
        workflow = self._load_workflow_for_project(project)
        paused_step = workflow.get_step(current_task.workflow_current_step)
        if paused_step is None or paused_step.role != "_builtin:human_gate":
            raise OrchestratorError(
                f"Task {task_id!r} is not paused on a resumable human-gate step."
            )

        transition = workflow.find_transition(paused_step.id, outcome)
        if transition is None:
            raise OrchestratorError(
                f"Workflow {workflow.id!r} has no `{outcome}` transition from "
                f"{paused_step.id!r}."
            )

        next_step = workflow.get_step(transition.to_step)
        if next_step is None:
            raise OrchestratorError(
                f"Workflow {workflow.id!r} is missing step {transition.to_step!r}."
            )

        carried_output = current_task.workflow_carried_output
        if outcome == "deny" and note:
            carried_output = note

        decision_detail = note or (
            "Approved by human." if outcome == "approve" else "Denied by human."
        )
        deferred = False
        if not next_step.role.startswith("_builtin:"):
            next_role = self.roles.get(next_step.role)
            if next_role is None:
                raise OrchestratorError(
                    f"Workflow {workflow.id!r} references unknown role {next_step.role!r}."
                )
            native_backend_available = (
                next_role.agent.backend in self.agent_runners
                and Path(project.repo_path).is_dir()
            )
            deferred = (
                self.agent_executor is None
                and not native_backend_available
            )
        deferred = deferred or defer
        decision_run = self.records.create_system_run(
            current_task,
            workflow_step=paused_step.id,
            outcome=outcome,
            detail=decision_detail,
            role_id="_builtin:human_gate",
            agent_backend="human",
        )
        self.records.emit_event(
            decision_run,
            "workflow.transition",
            {
                "from_step": paused_step.id,
                "to_step": transition.to_step,
                "trigger": f"completion:{outcome}",
            },
        )
        event_payload = {
            "step": paused_step.id,
            "decision": outcome,
            "next_step": transition.to_step,
            "deferred": deferred,
        }
        if note:
            event_payload["note"] = note
        self.records.emit_event(
            decision_run,
            "workflow.resumed",
            event_payload,
        )

        # Persist human gate decision as a durable audit record
        human_decision = HumanGateDecision(
            id=new_id("hg"),
            task_id=current_task.id,
            project_id=project.id,
            workflow_step=paused_step.id,
            decision=outcome,
            note=note,
            decided_by="human",
            decided_at=utc_now_text(),
            run_id=decision_run.id,
        )
        self.store.save_human_gate_decision(human_decision)

        current_task.status = "in_progress"
        current_task.blocked_reason = None
        # One write: a crash between "decision recorded" and "next step
        # recorded" must not leave a task that restarts from its entry step.
        current_task.workflow_current_step = transition.to_step if deferred else None
        current_task.workflow_carried_output = carried_output if deferred else None
        self.tasks.save(current_task)

        if deferred:
            refreshed = self.store.get_task(current_task.id)
            if refreshed is None:
                raise OrchestratorError(
                    f"Task {current_task.id!r} disappeared during deferred resume."
                )
            return HumanGateResumeResult(
                task=refreshed,
                decision=outcome,
                paused_step=paused_step.id,
                next_step=transition.to_step,
                deferred=True,
                carried_output=carried_output,
                note=note,
            )

        # Every task gets its own branch and worktree from the engine, in both
        # selection modes (ADR-0012). In autonomous mode the agent chooses what
        # to work on, not where: without a worktree it would run in the
        # operator's checkout and commit to whatever is checked out there.
        current_task.branch_name = current_task.branch_name or generate_branch_name(
            current_task
        )
        self.task_worktrees.ensure(project, current_task)

        self.runner.run_from_step(
            project,
            workflow,
            current_task,
            step=transition.to_step,
            carried_output=carried_output,
        )
        refreshed = self.store.get_task(current_task.id)
        if refreshed is None:
            raise OrchestratorError(
                f"Task {current_task.id!r} disappeared during human-gate resume."
            )
        latest_run = self.store.get_latest_run(refreshed.id)
        if latest_run is not None:
            self.runner.write_runtime_context(
                latest_run,
                project,
                context_projection=build_project_context(
                    self.store,
                    project,
                    current_task=refreshed,
                    carried_output=refreshed.workflow_carried_output,
                    mirror_dirs=context_mirror_dirs(project, refreshed),
                ),
            )
        return HumanGateResumeResult(
            task=refreshed,
            decision=outcome,
            paused_step=paused_step.id,
            next_step=transition.to_step,
            deferred=False,
            carried_output=carried_output,
            note=note,
        )

    # ── phases of one step ───────────────────────────────────────────────

    # ── Sprint advancement ────────────────────────────────────────────────────

    def _load_workflow_for_project(self, project: Project) -> WorkflowDefinition:
        workflow = self.workflows.get(project.workflow_id)
        if workflow is None:
            raise OrchestratorError(
                f"Unknown workflow {project.workflow_id!r} for project {project.id!r}."
            )
        return workflow

def generate_branch_name(task: Task) -> str:
    """Generate a stable branch name for one task."""

    prefix = _BRANCH_PREFIXES.get(task.task_type, "feat")
    return f"{prefix}/{task.id}"

