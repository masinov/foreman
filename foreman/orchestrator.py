"""Task orchestration for Foreman workflow execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from .builtins import BuiltinEventRecord, BuiltinExecutor
from .context import (
    ProjectContextProjection,
    build_project_context,
    relative_project_path,
)
from .engine.errors import (
    LeaseLostError,
    OrchestratorError,
    QuotaPauseError,
    TaskCancelledError,
    TaskExecutionError,
)
from .engine.agent_step import DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS, AgentStepRunner
from .engine.branch_sync import (
    context_mirror_dirs,
    prepare_task_branch_for_step,
    task_working_dir,
)
from .engine.evidence import EvidenceBuilder, branch_diff_content
from .engine.gates import blocked_reason_for_unhandled_outcome, gate_policy_decision
from .engine.leasing import TASK_LEASE_HEARTBEAT_SECONDS, TaskLeases
from .engine.limits import (
    resolve_project_settings,
)
from .engine.model_selection import (
    resolve_step_model_selection,
)
from .engine.output_contract import (
    contract_retry_reason,
    with_retry_instruction,
)
from .engine.prompts import (
    load_repo_instructions,
    safe_changed_files,
    safe_git_status,
    safe_recent_commits,
)
from .engine.records import RunRecords, new_id
from .engine.retention import Retention
from .engine.sprints import SprintFlow
from .engine.task_writes import TaskWrites
from .engine.recovery import Recovery
from .engine.selection import AUTONOMOUS_PLACEHOLDER_TITLE, TaskSelector
from .engine.signals import SignalHandler
from .engine.results import (
    AgentExecutionResult,
    AgentExecutor,
    HumanGateResumeResult,
    ProjectRunResult,
    quota_run_result,
)
from .errors import EngineCommandInterrupt
from .git import (
    GitError,
    task_commits_on_default_branch,
    branch_exists,
    head_sha,
    worktree_branch,
)
from .logs import get_logger
from .guidance import GUIDANCE_DELIVERED_EVENT, pending_guidance, prompt_with_guidance
from .models import CompletionEvidence, Event, HumanGateDecision, Project, Run, Task, utc_now_text
from .notifications import NotificationDispatcher
from .policy import PolicyMatrix, describe_resolution
from .outcomes import APPROVE, BLOCKED, DENY, ERROR, normalize_agent_outcome, normalize_reviewer_decision
from .runner import ClaudeCodeRunner, CodexRunner
from .runner.base import AgentRunner as NativeAgentRunner
from .runner.process import EngineShutdown
from .roles import RoleDefinition, default_roles_dir, load_roles
from .store import ForemanStore
from .workflows import WorkflowDefinition, WorkflowStep, default_workflows_dir, load_workflows
from .worktrees import (
    WorktreeError,
    WorktreeManager,
    enforce_worktree_limit,
    task_slug,
)

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
        self._worktree_managers: dict[str, WorktreeManager] = {}
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

    def select_next_task(self, project: Project) -> Task | None:
        """Pick and lease the next runnable task (see ``engine.selection``)."""

        return self.selector.select_next_task(project)

    def recover_orphaned_tasks(self, project_id: str) -> None:
        """Reset tasks an earlier engine left mid-work (see ``engine.recovery``)."""

        self.recovery.recover_orphaned_tasks(project_id)

    def worktrees(self, project: Project) -> WorktreeManager:
        """Return the worktree manager for one project, created once per run."""

        manager = self._worktree_managers.get(project.id)
        if manager is None or manager.project.repo_path != project.repo_path:
            manager = WorktreeManager(project)
            self._worktree_managers[project.id] = manager
        return manager

    def build_completion_evidence(
        self, task: Task, project: Project
    ) -> CompletionEvidence | None:
        """Build completion evidence for one task (see ``engine.evidence``)."""

        return self.evidence.build(task, project)

    def _ensure_task_worktree(self, project: Project, task: Task) -> Path | None:
        """Return the task's own checkout, creating it on the first develop visit.

        Every agent step, every test run, and every branch invariant works in
        this tree. The operator's checkout is never checked out or merged by
        the engine, so a person editing it — or a second engine — cannot
        corrupt a run. Existing in-progress tasks get a worktree here on their
        next visit; their branch already exists, so the tree is just added.
        """

        if not task.branch_name:
            return None
        manager = self.worktrees(project)
        if not manager.is_git_repository():
            return None
        self._reclaim_worktrees_for(project, task, manager)
        path = manager.ensure(task)
        recorded = str(path)
        if task.worktree_path != recorded:
            task.worktree_path = recorded
            self.tasks.save(task)
        return path

    def _reclaim_worktrees_for(
        self,
        project: Project,
        task: Task,
        manager: WorktreeManager,
    ) -> None:
        """Make room under ``max_live_worktrees`` before this task's tree exists.

        Enforced here rather than after the fact so the cap bounds peak disk
        use, not just its steady state. A reclaim is invisible to the task that
        loses its tree — the branch keeps the work and the next visit recreates
        the checkout — so it is recorded, not raised.
        """

        try:
            outcome = enforce_worktree_limit(
                self.store, project, keep_slug=task_slug(task), manager=manager
            )
        except WorktreeError as exc:
            # Reclaiming is an optimisation; failing it must not stop the task
            # that was about to run from getting its worktree.
            self._emit_worktree_event(
                task,
                "engine.worktree_reclaim_failed",
                {"error": str(exc)},
                detail=f"Could not enforce max_live_worktrees: {exc}",
            )
            return

        if outcome.reclaimed:
            self._emit_worktree_event(
                task,
                "engine.worktrees_reclaimed",
                {
                    "limit": outcome.limit,
                    "live_before": outcome.live_before,
                    "live_after": outcome.live_after,
                    "reclaimed": [entry.slug for entry in outcome.reclaimed],
                },
                detail=(
                    f"Reclaimed {len(outcome.reclaimed)} worktree(s) to stay under "
                    f"max_live_worktrees={outcome.limit}."
                ),
            )
        if outcome.over_limit:
            # Not a failure: the alternative was destroying uncommitted work.
            self._emit_worktree_event(
                task,
                "engine.worktree_limit_exceeded",
                {
                    "limit": outcome.limit,
                    "live_after": outcome.live_after,
                    "retained_dirty": [
                        entry.slug for entry in outcome.retained_dirty
                    ],
                },
                detail=(
                    f"{outcome.live_after} worktrees exceed max_live_worktrees="
                    f"{outcome.limit}; "
                    f"{len(outcome.retained_dirty)} hold uncommitted work and were "
                    f"kept."
                ),
            )

    def _emit_worktree_event(
        self,
        task: Task,
        event_type: str,
        payload: dict[str, Any],
        *,
        detail: str,
    ) -> None:
        """Record one worktree-lifecycle event against a synthetic system run."""

        run = self.records.create_system_run(
            task,
            workflow_step="orchestrator",
            outcome="success",
            detail=detail,
        )
        self.records.emit_event(run, event_type, payload)

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
        self._preflight_worktrees(project)
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

    def _pause_for_quota(
        self,
        project: Project,
        task: Task,
        run: Run,
        *,
        step: str,
        carried_output: str | None,
        result: AgentExecutionResult,
    ) -> None:
        """Park one task at its current step until the backend quota resets.

        The visit that hit the quota did no work, so it is not charged against
        the step-visit budget; the task keeps ``in_progress`` with its resume
        point persisted the way a human gate persists it, and its lease is
        released so the next pass (this engine or another) can resume it.
        """

        counts = dict(task.step_visit_counts)
        if counts.get(step, 0) > 0:
            counts[step] -= 1
        task.step_visit_counts = counts
        task.status = "in_progress"
        task.blocked_reason = None
        task.workflow_current_step = step
        task.workflow_carried_output = carried_output
        self.tasks.save(task)
        self.records.emit_event(
            run,
            "engine.quota_exhausted",
            {
                "step": step,
                "role_id": run.role_id,
                "retry_after": result.retry_after,
                "error": result.detail,
            },
        )
        self.leases.release(task, project)

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
        self._ensure_task_worktree(project, current_task)

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
        self.run_workflow_from_step(
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
            self._write_runtime_context(
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
        self._ensure_task_worktree(project, current_task)

        self.run_workflow_from_step(
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
            self._write_runtime_context(
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

    def run_workflow_from_step(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
        *,
        step: str,
        carried_output: str | None,
    ) -> Task:
        """Execute a workflow from one step until completion or a block."""

        try:
            return self._run_workflow_steps(
                project, workflow, task, step=step, carried_output=carried_output
            )
        except TaskCancelledError:
            # An operator cancelled the task while a step was running or
            # between two writes. Their decision stands: settle what the
            # engine left open and walk away without touching the task.
            return self._abandon_cancelled_task(project, task)
        except (
            EngineCommandInterrupt,
            EngineShutdown,
            KeyboardInterrupt,
            LeaseLostError,
            QuotaPauseError,
        ):
            # Each of these settles its own run on the way out.
            raise
        except Exception as exc:
            # Anything else escaped between a run being opened and closed (a
            # git failure in a built-in, an unknown built-in, a bookkeeping
            # error). Left ``running``, the run made the task refuse to start
            # again until the stale-run window passed.
            self._settle_open_runs(task.id, detail=f"Step failed with an engine error: {exc}")
            raise

    def _settle_open_runs(self, task_id: str, *, detail: str) -> None:
        """Mark every run still ``running`` for a task as failed."""

        for run in self.store.list_runs(task_id=task_id, status="running"):
            self.records.complete_run(
                run,
                status="failed",
                outcome=ERROR,
                detail=detail,
                session_id=self.records.session_id_from_events(run) or run.session_id,
                failure_type="infrastructure",
            )

    def _abandon_cancelled_task(self, project: Project, task: Task) -> Task:
        """Close the engine's open work on a task an operator cancelled."""

        for run in self.store.list_runs(task_id=task.id):
            if run.status == "running":
                self.records.complete_run(
                    run,
                    status="killed",
                    outcome=ERROR,
                    detail="Task was cancelled while this step was running.",
                    session_id=run.session_id,
                )
        self.leases.release(task, project)
        refreshed = self.store.get_task(task.id)
        if refreshed is None:
            raise OrchestratorError(f"Task {task.id!r} disappeared during execution.")
        return refreshed

    def _run_workflow_steps(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
        *,
        step: str,
        carried_output: str | None,
    ) -> Task:
        current_task = self.store.get_task(task.id) or task
        current_step = step
        session_ids: dict[tuple[str, str], str] = {}

        while current_step is not None:
            # A step only starts for a task that is still the engine's to
            # work on. A person may have cancelled or blocked it, and an
            # agent may have reported a blocker during the previous step.
            stored = self.tasks.adopt_operator_changes(current_task)
            if stored.status == "cancelled":
                raise TaskCancelledError(current_task.id)
            if stored.status == "blocked":
                current_task.status = stored.status
                current_task.blocked_reason = stored.blocked_reason
                self.leases.release(current_task, project)
                return stored

            step_def = workflow.get_step(current_step)
            if step_def is None:
                raise OrchestratorError(
                    f"Workflow {workflow.id!r} is missing step {current_step!r}."
                )

            # ── Before every step: enforce branch invariants ─────────────────
            default_branch = project.default_branch
            original_default_sha = head_sha(project.repo_path, f"refs/heads/{default_branch}")
            refreshed_default_sha: str | None = None

            # Verify the task's own worktree exists and sits on the task branch.
            # The operator's checkout is not consulted: what is checked out
            # there is none of the engine's business.
            if step_def.role not in {"_builtin:merge", "_builtin:mark_done"}:
                if current_task.branch_name:
                    try:
                        worktree_path = self._ensure_task_worktree(project, current_task)
                        if worktree_path is None:
                            raise OrchestratorError(
                                f"Task branch {current_task.branch_name!r} has no worktree."
                            )
                        if not branch_exists(project.repo_path, current_task.branch_name):
                            raise OrchestratorError(
                                f"Task branch {current_task.branch_name!r} does not exist."
                            )
                        active_branch = worktree_branch(worktree_path)
                        if active_branch != current_task.branch_name:
                            raise OrchestratorError(
                                f"Worktree {worktree_path} should be on task branch "
                                f"{current_task.branch_name!r} but is on {active_branch!r}."
                            )
                    except (OrchestratorError, WorktreeError, GitError) as e:
                        run = self.records.create_system_run(
                            current_task,
                            workflow_step=current_step,
                            outcome="blocked",
                            detail=str(e),
                        )
                        self.records.emit_event(
                            run,
                            "engine.branch_violation",
                            {
                                "branch": current_task.branch_name,
                                "detail": str(e),
                            },
                        )
                        current_task.status = "blocked"
                        current_task.blocked_reason = str(e)
                        current_task.workflow_current_step = None
                        current_task.workflow_carried_output = None
                        self.tasks.save(current_task)
                        current_step = None
                        self.leases.release(current_task, project)
                        break

            visit_count = current_task.step_visit_counts.get(current_step, 0) + 1
            current_task.step_visit_counts[current_step] = visit_count
            self.tasks.save(current_task)

            settings = resolve_project_settings(project)
            max_step_visits = settings.max_step_visits
            if visit_count > max_step_visits:
                detail = (
                    f"Step '{current_step}' visited {visit_count} times "
                    f"(limit: {max_step_visits}). Stuck in a loop."
                )
                run = self.records.create_system_run(
                    current_task,
                    workflow_step=current_step,
                    outcome="blocked",
                    detail=detail,
                    attention_trigger="loop_limit",
                )
                self.records.emit_event(
                    run,
                    "workflow.loop_limit",
                    {
                        "step": current_step,
                        "visit_count": visit_count,
                        "max_visits": max_step_visits,
                    },
                )
                current_task.status = "blocked"
                current_task.blocked_reason = detail
                self.tasks.save(current_task)
                break

            task_cost = sum(run.cost_usd for run in self.store.list_runs(task_id=current_task.id))
            cost_limit = settings.cost_limit_per_task_usd
            # 0 is the documented "off" value, and what the settings screen saves.
            if cost_limit > 0 and task_cost >= cost_limit:
                detail = f"Task cost ${task_cost:.2f} exceeds limit ${cost_limit:.2f}"
                run = self.records.create_system_run(
                    current_task,
                    workflow_step=current_step,
                    outcome="blocked",
                    detail=detail,
                )
                self.records.emit_event(
                    run,
                    "gate.cost_exceeded",
                    {
                        "limit_usd": cost_limit,
                        "actual_usd": task_cost,
                        "scope": "task",
                    },
                )
                current_task.status = "blocked"
                current_task.blocked_reason = detail
                self.tasks.save(current_task)
                break

            sprint_cost_limit = settings.cost_limit_per_sprint_usd
            sprint_cost = float(
                self.store.run_totals(sprint_id=current_task.sprint_id)["total_cost_usd"]
            )
            if (
                sprint_cost_limit > 0
                and sprint_cost >= sprint_cost_limit
            ):
                detail = (
                    f"Sprint cost ${sprint_cost:.2f} exceeds limit "
                    f"${sprint_cost_limit:.2f}"
                )
                run = self.records.create_system_run(
                    current_task,
                    workflow_step=current_step,
                    outcome="blocked",
                    detail=detail,
                )
                self.records.emit_event(
                    run,
                    "gate.cost_exceeded",
                    {
                        "limit_usd": sprint_cost_limit,
                        "actual_usd": sprint_cost,
                        "scope": "sprint",
                    },
                )
                current_task.status = "blocked"
                current_task.blocked_reason = detail
                self.tasks.save(current_task)
                break

            task_duration_ms = sum(
                run.duration_ms or 0
                for run in self.store.list_runs(task_id=current_task.id)
            )
            time_limit_ms = settings.time_limit_per_task_ms
            if time_limit_ms > 0 and task_duration_ms >= time_limit_ms:
                detail = f"Task time {task_duration_ms/1000:.1f}s exceeds limit {time_limit_ms/1000:.1f}s"
                run = self.records.create_system_run(
                    current_task,
                    workflow_step=current_step,
                    outcome="blocked",
                    detail=detail,
                )
                self.records.emit_event(
                    run,
                    "gate.time_exceeded",
                    {
                        "task_id": current_task.id,
                        "total_duration_ms": task_duration_ms,
                        "time_limit_ms": time_limit_ms,
                    },
                )
                current_task.status = "blocked"
                current_task.blocked_reason = detail
                self.tasks.save(current_task)
                break

            branch_sync_event: tuple[str, dict[str, Any]] | None = None
            if current_task.branch_name and step_def.role not in {
                "_builtin:merge",
                "_builtin:mark_done",
            }:
                (
                    carried_output,
                    branch_sync_event,
                ) = prepare_task_branch_for_step(
                    project=project,
                    task=current_task,
                    step=current_step,
                    carried_output=carried_output,
                )
                # What the refresh may just have merged into the task branch.
                refreshed_default_sha = head_sha(
                    project.repo_path, f"refs/heads/{default_branch}"
                )

            current_task.workflow_current_step = current_step
            current_task.workflow_carried_output = carried_output
            self.tasks.save(current_task)

            # Poll *after* the resume point is persisted: an interrupt here
            # must leave the task resumable at the step it was about to run,
            # not at the one it already finished.
            self._poll_commands(current_task.id)

            if step_def.role == "_builtin:human_gate":
                run = self.records.create_running_run(
                    current_task,
                    role_id=step_def.role,
                    workflow_step=current_step,
                    agent_backend="builtin",
                )
                self.records.emit_event(
                    run,
                    "workflow.step_started",
                    {"step": current_step, "visit_count": visit_count},
                )
                self._emit_policy_resolved(run, project, current_task)
                gate_policy = gate_policy_decision(project, current_task, step_def)
                if gate_policy == "auto":
                    outcome, detail = self._auto_approve_gate(
                        run, project, current_task, step_def
                    )
                else:
                    result = self.builtin_executor.execute(
                        step_def.role,
                        project=project,
                        task=current_task,
                        step_id=current_step,
                        carried_output=carried_output,
                        store=self.store,
                        event_recorder=lambda event_record: self._persist_builtin_event(run, event_record),
                        working_dir=task_working_dir(project, current_task),
                    )
                    self.tasks.save(current_task)
                    self.records.complete_run(
                        run,
                        status="completed",
                        outcome=result.outcome,
                        detail=result.detail,
                    )
                    self._emit_builtin_events(run, result.events)
                    self.records.emit_event(
                        run,
                        "workflow.paused",
                        {
                            "step": current_step,
                            "reason": "human_gate",
                            "policy": step_def.policy,
                            # What the project asked to be told about; the
                            # delivery worker acts on this persisted decision.
                            "notify": self.records.notification_policy(project, current_task),
                        },
                    )
                    # A task waiting for a person is not being worked on. Left
                    # held, the lease made the engine wait out its remaining
                    # lifetime before it could act on the decision.
                    self.leases.release(current_task, project)
                    return current_task

            elif step_def.role.startswith("_builtin:"):
                run = self.records.create_running_run(
                    current_task,
                    role_id=step_def.role,
                    workflow_step=current_step,
                    agent_backend="builtin",
                )
                self.records.emit_event(
                    run,
                    "workflow.step_started",
                    {"step": current_step, "visit_count": visit_count},
                )
                self._emit_policy_resolved(run, project, current_task)
                builtin_started = time.monotonic()
                result = self.builtin_executor.execute(
                    step_def.role,
                    project=project,
                    task=current_task,
                    step_id=current_step,
                    carried_output=carried_output,
                    store=self.store,
                    evidence_builder=self.build_completion_evidence,
                    working_dir=task_working_dir(project, current_task),
                )
                self.tasks.save(current_task)
                self.records.complete_run(
                    run,
                    status="completed",
                    outcome=result.outcome,
                    detail=result.detail,
                    # A test run or a merge takes real time; recording 0 made
                    # every built-in step look instantaneous.
                    duration_ms=int((time.monotonic() - builtin_started) * 1000),
                )
                self._emit_builtin_events(run, result.events)
                # A builtin that blocks (e.g. the merge/mark_done completion
                # guard rejecting weak evidence) sets the task to blocked itself
                # and never routes through ``_create_system_run``; raise the one
                # attention-needed turn here so supervision still fires.
                if result.outcome == BLOCKED:
                    self.records.emit_attention_needed(
                        run,
                        current_task.id,
                        self.records.attention_trigger_for_block(current_task),
                    )
                outcome = normalize_agent_outcome(result.outcome)
                detail = result.detail
            else:
                role = self.roles.get(step_def.role)
                if role is None:
                    raise OrchestratorError(f"Unknown role {step_def.role!r}.")
                current_task.assigned_role = role.id
                self.tasks.save(current_task)

                context_projection = build_project_context(
                    self.store,
                    project,
                    current_task=current_task,
                    carried_output=carried_output,
                    mirror_dirs=context_mirror_dirs(project, current_task),
                )
                prompt = self._build_prompt(
                    role,
                    project,
                    current_task,
                    carried_output,
                    context_projection=context_projection,
                )
                # Notes a person wrote for this task since the last agent step
                # go into this prompt, and are marked delivered once the run
                # that carries them exists.
                guidance = pending_guidance(self.store.list_events(task_id=current_task.id))
                prompt = prompt_with_guidance(prompt, guidance)
                model_selection = resolve_step_model_selection(
                    task=current_task,
                    role=role,
                    project=project,
                    step_id=current_step,
                    visit_count=visit_count,
                )
                model = model_selection.model or ""
                run = self.records.create_running_run(
                    current_task,
                    role_id=role.id,
                    workflow_step=current_step,
                    agent_backend=role.agent.backend,
                    model=model_selection.model,
                    branch_name=current_task.branch_name,
                    prompt_text=prompt,
                )
                self.records.emit_event(
                    run,
                    "workflow.model_selected",
                    {
                        "step": current_step,
                        "model": model_selection.model,
                        "visit_count": visit_count,
                        "source": model_selection.source,
                    },
                )
                self.records.emit_event(
                    run,
                    "engine.role_policy",
                    {
                        "role_id": role.id,
                        "backend": role.agent.backend,
                        "permission_mode": role.agent.permission_mode,
                        "disallowed_tools": list(role.agent.tools.disallowed),
                    },
                )
                self._write_runtime_context(
                    run,
                    project,
                    context_projection=context_projection,
                )
                self.records.emit_event(
                    run,
                    "agent.prompt",
                    {"text": prompt},
                    role_id=role.id,
                )
                if guidance:
                    self.records.emit_event(
                        run,
                        GUIDANCE_DELIVERED_EVENT,
                        {
                            "message_event_ids": [note.event_id for note in guidance],
                            "role": role.id,
                            "step": current_step,
                        },
                    )
                self.records.emit_event(
                    run,
                    "workflow.step_started",
                    {"step": current_step, "visit_count": visit_count},
                )
                self._emit_policy_resolved(run, project, current_task)
                if branch_sync_event is not None:
                    event_type, payload = branch_sync_event
                    self.records.emit_event(run, event_type, payload)
                session_key = (role.id, role.agent.backend)
                session_id: str | None = None
                if role.agent.session_persistence:
                    session_id = session_ids.get(session_key)
                    if session_id is None:
                        session_id = self.store.get_latest_session_id(
                            task_id=current_task.id,
                            role_id=role.id,
                            agent_backend=role.agent.backend,
                        )
                        if session_id:
                            session_ids[session_key] = session_id
                result = self.agent_steps.execute_guarded(
                    run=run,
                    role=role,
                    project=project,
                    task=current_task,
                    workflow_step=current_step,
                    prompt=prompt,
                    session_id=session_id,
                    carried_output=carried_output,
                    model=model_selection.model,
                    event_recorder=lambda event_record: self.signals.persist_agent_event(
                        run,
                        current_task,
                        project,
                        role.id,
                        event_record,
                    ),
                )
                if not result.events_streamed:
                    self.signals.emit_agent_events(run, current_task, project, role.id, result.events)
                self.records.complete_run(
                    run,
                    status=result.status,
                    outcome=result.outcome,
                    detail=result.detail,
                    model=result.model or model or None,
                    session_id=result.session_id,
                    cost_usd=result.cost_usd,
                    token_count=result.token_count,
                    token_usage=result.token_usage,
                    duration_ms=result.duration_ms,
                    retry_count=result.retry_count,
                    failure_type=result.failure_type,
                )
                retry_reason = (
                    None
                    if result.failure_type == "quota"
                    else contract_retry_reason(role, result)
                )
                if retry_reason is not None:
                    self.records.emit_event(
                        run,
                        "engine.output_contract_retry",
                        {
                            "step": current_step,
                            "role_id": role.id,
                            "reason": retry_reason,
                            "retry_attempt": 1,
                        },
                    )
                    retry_prompt = with_retry_instruction(
                        prompt,
                        role,
                        retry_reason,
                    )
                    retry_session_id = result.session_id or session_id
                    retry_run = self.records.create_running_run(
                        current_task,
                        role_id=role.id,
                        workflow_step=current_step,
                        agent_backend=role.agent.backend,
                        model=model or None,
                        branch_name=current_task.branch_name,
                        prompt_text=retry_prompt,
                    )
                    self._write_runtime_context(
                        retry_run,
                        project,
                        context_projection=context_projection,
                    )
                    self.records.emit_event(
                        retry_run,
                        "workflow.step_started",
                        {
                            "step": current_step,
                            "visit_count": visit_count,
                            "retry_attempt": 1,
                        },
                    )
                    retry_result = self.agent_steps.execute_guarded(
                        run=retry_run,
                        role=role,
                        project=project,
                        task=current_task,
                        workflow_step=current_step,
                        prompt=retry_prompt,
                        session_id=retry_session_id,
                        carried_output=carried_output,
                        model=model_selection.model,
                        event_recorder=lambda event_record: self.signals.persist_agent_event(
                            retry_run,
                            current_task,
                            project,
                            role.id,
                            event_record,
                        ),
                    )
                    if not retry_result.events_streamed:
                        self.signals.emit_agent_events(
                            retry_run,
                            current_task,
                            project,
                            role.id,
                            retry_result.events,
                        )
                    self.records.complete_run(
                        retry_run,
                        status=retry_result.status,
                        outcome=retry_result.outcome,
                        detail=retry_result.detail,
                        model=retry_result.model or model or None,
                        session_id=retry_result.session_id,
                        cost_usd=retry_result.cost_usd,
                        token_count=retry_result.token_count,
                        token_usage=retry_result.token_usage,
                        duration_ms=retry_result.duration_ms,
                        retry_count=retry_result.retry_count,
                        failure_type=retry_result.failure_type,
                    )
                    run = retry_run
                    result = retry_result
                if result.failure_type == "quota":
                    self._pause_for_quota(
                        project,
                        current_task,
                        run,
                        step=current_step,
                        carried_output=carried_output,
                        result=result,
                    )
                    raise QuotaPauseError(
                        current_task.id,
                        retry_after=result.retry_after,
                        detail=result.detail,
                    )
                if role.agent.session_persistence and result.session_id:
                    session_ids[session_key] = result.session_id
                if role.completion.output.extract_decision:
                    outcome = normalize_reviewer_decision(result.outcome)
                    # A decision is about the commit the reviewer saw. Record
                    # it, so evidence can tell an approval of the head commit
                    # from an approval of an earlier one.
                    self.records.emit_event(
                        run,
                        "engine.review_recorded",
                        {
                            "role": role.id,
                            "review_kind": role.completion.review_kind,
                            "outcome": outcome,
                            "head_sha": self.evidence.branch_head(project, current_task),
                        },
                    )
                else:
                    outcome = normalize_agent_outcome(result.outcome)
                detail = result.detail

            # ── Autonomous mode: an agent that never named its task ──
            # The agent is asked to report what it chose to work on with
            # signal.task_started. If it has not after a step that may send
            # that signal, the task goes on as it is (spec §6.2: degraded but
            # functional). The gap is recorded once, and what is recorded for
            # the task is read from the store, so a restart changes nothing.
            if (
                settings.task_selection_mode == "autonomous"
                and current_task.created_by == "orchestrator"
                and current_task.title == AUTONOMOUS_PLACEHOLDER_TITLE
                and step_def.role in self.roles
                and "task_started" in self.roles[step_def.role].signals
                and not self.signals.autonomous_gap_recorded(current_task)
            ):
                self.records.emit_event(
                    run,
                    "workflow.autonomous_contract_missing",
                    {
                        "task_id": current_task.id,
                        "step": current_step,
                        "reason": (
                            "The agent did not send signal.task_started, so the task "
                            "has no title or acceptance criteria of its own. The "
                            "workflow continues; review judges what the agent did."
                        ),
                    },
                )

            self.records.emit_event(
                run,
                "workflow.step_completed",
                {"step": current_step, "outcome": outcome},
            )

            # Evidence built for the reviewer's prompt predates the review. Now
            # that a decision exists, record it, so the task shows what was
            # decided rather than "no review yet" until the merge step.
            if (
                current_task.completion_evidence is not None
                and not step_def.role.startswith("_builtin:")
                and step_def.role in self.roles
                and self.roles[step_def.role].completion.output.extract_decision
            ):
                current_task.completion_evidence = self.build_completion_evidence(
                    current_task, project
                )
                self.tasks.save(current_task)

            # ── After every step: the task's own work must not be on the
            # default branch before the merge step puts it there. The default
            # branch itself may move (an operator commits, another task
            # merges); that is none of this task's business. ADR-0012.
            leaked_commits: tuple[str, ...] = ()
            if step_def.role != "_builtin:merge" and current_task.branch_name:
                leaked_commits = task_commits_on_default_branch(
                    project.repo_path,
                    task_branch=current_task.branch_name,
                    default_branch=default_branch,
                    default_shas_seen=(original_default_sha, refreshed_default_sha),
                )
            if leaked_commits:
                detail = (
                    f"{len(leaked_commits)} commit(s) from task branch "
                    f"{current_task.branch_name!r} are on {default_branch!r} before the "
                    f"merge step (first: {leaked_commits[0][:12]}). The task's work must "
                    "reach the default branch only through the workflow's merge."
                )
                run = self.records.create_system_run(
                    current_task,
                    workflow_step=current_step,
                    outcome="blocked",
                    detail=detail,
                )
                self.records.emit_event(
                    run,
                    "engine.branch_violation",
                    {
                        "branch": default_branch,
                        "detail": detail,
                        "commits": list(leaked_commits[:20]),
                    },
                )
                current_task.status = "blocked"
                current_task.blocked_reason = detail
                current_task.workflow_current_step = None
                current_task.workflow_carried_output = None
                self.tasks.save(current_task)
                current_step = None
                self.leases.release(current_task, project)
                break

            transition = workflow.find_transition(current_step, outcome)
            if transition is None:
                if current_task.status == "done":
                    current_task.workflow_current_step = None
                    current_task.workflow_carried_output = None
                    self.tasks.save(current_task)
                    current_step = None
                    self.leases.release(current_task, project)
                    break

                self.records.emit_event(
                    run,
                    "workflow.no_transition",
                    {"step": current_step, "outcome": outcome},
                )
                current_task.status = "blocked"
                current_task.blocked_reason = blocked_reason_for_unhandled_outcome(
                    workflow=workflow,
                    step=current_step,
                    outcome=outcome,
                    detail=detail,
                )
                current_task.workflow_current_step = None
                current_task.workflow_carried_output = None
                self.tasks.save(current_task)
                current_step = None
                self.leases.release(current_task, project)
                continue

            self.records.emit_event(
                run,
                "workflow.transition",
                {
                    "from_step": current_step,
                    "to_step": transition.to_step,
                    "trigger": transition.trigger,
                },
            )
            carried_output = detail if transition.carry_output else None
            if transition.trigger == "completion:conflict":
                current_task.step_visit_counts = {}
                self.records.emit_event(
                    run,
                    "workflow.step_visit_reset",
                    {
                        "reason": "merge_conflict_recovery",
                        "from_step": current_step,
                        "to_step": transition.to_step,
                    },
                )
            # The next step is recorded in the same write that leaves this
            # one. A crash before that step starts then resumes there; with
            # the step cleared first, recovery restarted the whole task and
            # an approval recorded a moment earlier was lost.
            current_task.workflow_current_step = transition.to_step
            current_task.workflow_carried_output = (
                carried_output if transition.to_step is not None else None
            )
            self.tasks.save(current_task)
            current_step = transition.to_step

            # Renew lease after each step (heartbeat during workflow execution).
            if current_step is not None:
                self.leases.renew(current_task, project)

        # Every path that parks a task leaves it ``blocked``: a gate, a loop
        # or cost limit, a failed guard. A parked task is not being worked on,
        # so nothing may keep holding (and heartbeating) its lease.
        if current_task.status == "blocked":
            self.leases.release(current_task, project)

        return current_task

    def _emit_policy_resolved(self, run: Run, project: Project, task: Task) -> None:
        """Record the resolved policy matrix once, on the task's first step.

        The audit trail should answer why a person was (or was not) asked, not
        only that they were, so every decision is written with the layer that
        produced it. Written once per task: resuming a paused task does not
        re-resolve anything a reader has not already seen.
        """

        if self.store.has_event(task_id=task.id, event_type="policy.resolved"):
            return
        resolved = PolicyMatrix.for_project(project).resolve_task(task)
        self.records.emit_event(
            run,
            "policy.resolved",
            {
                "task_type": task.task_type,
                "decisions": describe_resolution(resolved),
            },
        )

    def _auto_approve_gate(
        self,
        run: Run,
        project: Project,
        task: Task,
        step: WorkflowStep,
    ) -> tuple[str, str]:
        """Approve a policy-governed gate on the engine's behalf, with an audit record."""

        detail = f"Auto-approved by policy ({step.policy}=auto)."
        self.records.emit_event(
            run,
            "workflow.gate_auto_approved",
            {"step": step.id, "policy": step.policy},
        )
        self.records.complete_run(run, status="completed", outcome=APPROVE, detail=detail)
        self.store.save_human_gate_decision(
            HumanGateDecision(
                id=new_id("hg"),
                task_id=task.id,
                project_id=project.id,
                workflow_step=step.id,
                decision="approve",
                note=detail,
                decided_by=f"policy:{step.policy}",
                decided_at=utc_now_text(),
                run_id=run.id,
            )
        )
        return (APPROVE, detail)

    def _preflight_worktrees(self, project: Project) -> None:
        """Fail a run at the start when the repository cannot host worktrees.

        Every task runs in a Foreman-owned worktree, so a git that is too old
        or a worktree root git would try to commit is a project-level problem.
        Discovering it here, before any task is leased, gives the operator one
        clear message instead of a task blocked halfway through a step.
        """

        try:
            self.worktrees(project).preflight()
        except WorktreeError as exc:
            raise OrchestratorError(str(exc)) from exc

    # ── Sprint advancement ────────────────────────────────────────────────────

    def _latest_agent_run(self, task_id: str) -> Run | None:
        """Return the most recent completed agent (non-builtin) run for a task.

        Prompts that quote the "previous output" want the last thing an agent
        said, not the output of the test or merge built-in that ran after it.
        """

        candidates = [
            run
            for run in self.store.list_runs(task_id=task_id)
            if not run.role_id.startswith("_builtin:")
            and run.status == "completed"
            and run.outcome_detail
        ]
        return candidates[-1] if candidates else None

    def _load_workflow_for_project(self, project: Project) -> WorkflowDefinition:
        workflow = self.workflows.get(project.workflow_id)
        if workflow is None:
            raise OrchestratorError(
                f"Unknown workflow {project.workflow_id!r} for project {project.id!r}."
            )
        return workflow

    def _build_prompt(
        self,
        role: RoleDefinition,
        project: Project,
        task: Task,
        carried_output: str | None,
        *,
        context_projection: ProjectContextProjection | None = None,
    ) -> str:
        latest_run = self._latest_agent_run(task.id)
        if context_projection is None:
            context_projection = build_project_context(
                self.store,
                project,
                current_task=task,
                carried_output=carried_output,
            )
        # Reuse cached evidence on the task record to avoid recomputing on
        # repeated reviewer prompts. Built once at first reviewer render.
        evidence = task.completion_evidence
        if evidence is not None and self.evidence.is_stale(evidence, task, project):
            evidence = None
            task.completion_evidence = None
        if evidence is None and role.completion.output.extract_decision:
            evidence = self.build_completion_evidence(task, project)
            task.completion_evidence = evidence
            self.tasks.save(task)
        context = {
            "task_title": task.title,
            "task_description": task.description or "",
            "task_type": task.task_type,
            "acceptance_criteria": task.acceptance_criteria or "",
            "branch_name": task.branch_name or "",
            "sprint_context": context_projection.context_markdown,
            "project_status": context_projection.status_markdown,
            "repo_instructions": load_repo_instructions(project.repo_path),
            "spec_path": project.spec_path or "",
            "previous_feedback": carried_output or "",
            "previous_output": latest_run.outcome_detail if latest_run else "",
            # Status describes the tree the agent works in; diffs and log come
            # from refs, which every worktree shares.
            "git_status": safe_git_status(task_working_dir(project, task)),
            "changed_files": safe_changed_files(
                project.repo_path,
                project.default_branch,
                task.branch_name,
            ),
            "recent_commits": safe_recent_commits(project.repo_path, task.branch_name),
            "completion_evidence": (
                str(evidence)
                if role.completion.output.extract_decision
                and task.branch_name
                and evidence is not None
                else ""
            ),
            # Curated diff payload, only for decision roles so they can review
            # the change without exploring the repo. Other roles get "".
            "completion_diff": (
                branch_diff_content(
                    project.repo_path,
                    project.default_branch,
                    task.branch_name,
                    max_chars=resolve_project_settings(project).review_diff_max_chars,
                )
                if role.completion.output.extract_decision and task.branch_name
                else ""
            ),
        }
        if evidence is not None:
            context.update({
                "completion_proof_status": evidence.proof_status,
                "completion_tests_status": evidence.tests_status,
                "completion_review_outcome": evidence.review_outcome,
                "completion_criteria_count": evidence.criteria_count,
                "completion_criteria_addressed": evidence.criteria_addressed,
                "completion_criteria_partially_addressed": evidence.criteria_partially_addressed,
                "completion_changed_files": evidence.changed_files,
                "completion_branch_diff_stat": evidence.branch_diff_stat,
                "completion_builtin_test_passed": evidence.builtin_test_passed,
                "completion_builtin_test_result": evidence.builtin_test_result,
                "completion_builtin_test_detail": evidence.builtin_test_detail,
            })
        return role.render_prompt(context)

    def _write_runtime_context(
        self,
        run: Run,
        project: Project,
        *,
        context_projection: ProjectContextProjection,
    ) -> None:
        context_projection.write()
        for path in context_projection.written_paths:
            self.records.emit_event(
                run,
                "engine.context_write",
                {"path": relative_project_path(project, path)},
            )

    def _emit_builtin_events(
        self,
        run: Run,
        events: tuple[BuiltinEventRecord, ...],
    ) -> None:
        for event_record in events:
            payload = dict(event_record.payload)
            payload["schema_version"] = event_record.schema_version
            self.records.emit_event(run, event_record.event_type, payload)

    def _persist_builtin_event(
        self,
        run: Run,
        event_record: BuiltinEventRecord,
    ) -> None:
        """Persist one builtin event immediately while the builtin step is active."""

        payload = dict(event_record.payload)
        payload["schema_version"] = event_record.schema_version
        self.records.emit_event(run, event_record.event_type, payload)

def generate_branch_name(task: Task) -> str:
    """Generate a stable branch name for one task."""

    prefix = _BRANCH_PREFIXES.get(task.task_type, "feat")
    return f"{prefix}/{task.id}"

