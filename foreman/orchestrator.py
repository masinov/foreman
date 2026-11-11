"""Task orchestration for Foreman workflow execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re
import subprocess
import time
from typing import Any, Protocol
from uuid import uuid4

from .builtins import BuiltinEventRecord, BuiltinExecutor
from .context import (
    ProjectContextProjection,
    build_project_context,
    context_directory,
    relative_project_path,
)
from .errors import EngineCommandInterrupt, ForemanError
from .git import (
    GitError,
    task_commits_on_default_branch,
    commits_behind,
    merge_in_progress,
    branch_exists,
    changed_files,
    head_sha,
    is_worktree_clean,
    recent_commits,
    status_text,
    sync_branch_with_base,
    worktree_branch,
)
from .leases import generate_lease_token
from .logs import compact_payload, event_log_level, get_logger, log_event
from .guidance import GUIDANCE_DELIVERED_EVENT, pending_guidance, prompt_with_guidance
from .judge import NOT_JUDGED, judge_criteria, truncate_diff
from .models import CompletionEvidence, Event, HumanGateDecision, Lease, Project, Run, Sprint, TASK_COMPLEXITIES, Task, TokenUsage, utc_now_text
from .task_lease import TaskLeaseHeartbeat
from .notifications import NotificationDispatcher, resolve_notification_policy
from .policy import GATE_DECISIONS, PolicyMatrix, describe_resolution
from .outcomes import APPROVE, BLOCKED, DENY, DONE, ERROR, normalize_agent_outcome, normalize_reviewer_decision
from .runner import AgentRunConfig, ClaudeCodeRunner, CodexRunner, PreflightError, run_with_retry
from .runner.base import AgentRunner as NativeAgentRunner
from .runner.process import EngineShutdown
from .runner.env import resolve_env
from .roles import RoleDefinition, default_roles_dir, load_roles
from .settings import ProjectSettings, SettingsError
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


class OrchestratorError(ForemanError):
    """Raised when Foreman cannot execute the requested workflow slice."""


class TaskCancelledError(OrchestratorError):
    """The task was cancelled by an operator while the engine was working on it."""

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task {task_id!r} was cancelled; the engine stopped working on it.")
        self.task_id = task_id


class LeaseLostError(OrchestratorError):
    """Raised when this engine's task lease is renewed and found to be gone.

    Another engine has taken the task over, or the lease expired while the
    agent was silent. The active agent is stopped and this engine exits
    without touching the task, which the new holder now owns.
    """


class QuotaPauseError(OrchestratorError):
    """Raised when a task must pause because the agent backend's quota ran out.

    The task keeps its resume point (``workflow_current_step`` and the carried
    output) and its ``in_progress`` status, so the next pass resumes it at the
    same step; nothing about the task itself failed. ``retry_after`` is the
    backend's reset time when it reported one.
    """

    def __init__(self, task_id: str, *, retry_after: str | None, detail: str) -> None:
        super().__init__(f"Task {task_id!r} paused until the backend quota resets: {detail}")
        self.task_id = task_id
        self.retry_after = retry_after
        self.detail = detail


class TaskExecutionError(OrchestratorError):
    """Raised when running one specific task failed.

    Carries the task identifier so a resident engine can isolate the failure:
    block that one task, raise an attention turn for it, and keep serving the
    rest of the project instead of exiting. A one-shot ``foreman run`` treats
    it like any other ``OrchestratorError``.
    """

    def __init__(self, task_id: str, cause: BaseException) -> None:
        super().__init__(f"Task {task_id!r} failed: {cause}")
        self.task_id = task_id
        self.cause = cause


@dataclass(slots=True)
class AgentEventRecord:
    """One structured event returned from an agent executor."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now_text)


@dataclass(slots=True)
class AgentExecutionResult:
    """Normalized output from one agent workflow step."""

    outcome: str
    detail: str = ""
    status: str = "completed"
    session_id: str | None = None
    cost_usd: float = 0.0
    token_count: int = 0
    token_usage: TokenUsage | None = None
    duration_ms: int | None = None
    model: str | None = None
    events: tuple[AgentEventRecord, ...] = ()
    events_streamed: bool = False
    retry_count: int = 0
    #: ``quota`` | ``preflight`` | ``infrastructure`` | ``agent`` when the run failed.
    failure_type: str | None = None
    #: ISO 8601 UTC time after which a quota failure may be retried.
    retry_after: str | None = None


@dataclass(slots=True)
class ProjectRunResult:
    """Summary of one orchestrator invocation."""

    project_id: str
    executed_task_ids: tuple[str, ...]
    blocked_task_ids: tuple[str, ...]
    stop_reason: str
    #: Set with ``stop_reason="quota_exhausted"``: when the backend said it will serve again.
    retry_after: str | None = None
    detail: str | None = None


@dataclass(slots=True)
class HumanGateResumeResult:
    """Summary of one human-gate decision and any resumed execution."""

    task: Task
    decision: str
    paused_step: str
    next_step: str
    deferred: bool
    carried_output: str | None = None
    note: str | None = None


class AgentExecutor(Protocol):
    """Execution protocol for workflow agent steps."""

    def execute(
        self,
        *,
        role: RoleDefinition,
        project: Project,
        task: Task,
        workflow_step: str,
        prompt: str,
        session_id: str | None,
        carried_output: str | None,
    ) -> AgentExecutionResult:
        """Execute one agent step and return normalized results."""


class ForemanOrchestrator:
    """Drive persisted tasks through declarative workflows."""

    # Minimum interval (seconds) between task-lease renewals while a native
    # runner step is streaming. The default 30s is well under the 5-minute lease
    # duration so a long Claude/Codex stream keeps the lease alive.
    _DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS = 30.0

    # Maximum heartbeat age (seconds) below which a lease is still considered
    # alive for active-run recovery. If the lease's heartbeat is older than
    # this window, recovery treats the holder as gone even if the lease is
    # technically still within its ``expires_at`` window.
    _LEASE_LIVENESS_THRESHOLD_SECONDS = 60.0
    # Well inside both the 300-second lease and the 60-second liveness window
    # above; see foreman/task_lease.py.
    _TASK_LEASE_HEARTBEAT_SECONDS = 20.0

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
        self.runner_sleep = runner_sleep
        self.utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self.holder_id = holder_id or str(uuid4())
        if native_step_heartbeat_seconds is not None and native_step_heartbeat_seconds < 0:
            native_step_heartbeat_seconds = 0.0
        self._native_step_heartbeat_seconds = (
            native_step_heartbeat_seconds
            if native_step_heartbeat_seconds is not None
            else self._DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS
        )
        self._task_lease_tokens: dict[str, str] = {}
        self._task_lease_heartbeats: dict[str, TaskLeaseHeartbeat] = {}
        self._task_started_received: set[str] = set()
        self._developer_step_executed: set[str] = set()
        self._worktree_managers: dict[str, WorktreeManager] = {}
        #: Called with the running task id before every workflow step and on
        #: every silent-agent tick. The resident engine supplies it so an
        #: operator's `pause` or `stop_task` reaches an agent that may run for
        #: an hour. It returns normally to continue and raises
        #: ``EngineCommandInterrupt`` to stop the step. A one-shot ``foreman
        #: run`` leaves it None and behaves exactly as before.
        self.command_poll = command_poll

    def worktrees(self, project: Project) -> WorktreeManager:
        """Return the worktree manager for one project, created once per run."""

        manager = self._worktree_managers.get(project.id)
        if manager is None or manager.project.repo_path != project.repo_path:
            manager = WorktreeManager(project)
            self._worktree_managers[project.id] = manager
        return manager

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
            self._save_task(task)
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

        run = self._create_system_run(
            task,
            workflow_step="orchestrator",
            outcome="success",
            detail=detail,
        )
        self._emit_event(run, event_type, payload)

    def _task_working_dir(self, project: Project, task: Task) -> Path:
        """Return the directory a step for this task should run in."""

        recorded = task.worktree_path
        if recorded and Path(recorded).is_dir():
            return Path(recorded)
        return Path(project.repo_path)

    def _context_mirror_dirs(self, project: Project, task: Task) -> tuple[Path, ...]:
        """Return the worktree context directory the projection is mirrored into."""

        working_dir = self._task_working_dir(project, task)
        if working_dir == Path(project.repo_path):
            return ()
        return (context_directory(project, root=working_dir),)

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

    def _save_task(self, task: Task, *, include_definition: bool = False) -> None:
        """Persist the engine's view of a task without overwriting an operator's.

        Only workflow state is written (see ``update_task_engine_state``). A
        task the store does not know yet is inserted whole. A task an operator
        cancelled is left exactly as it is and ``TaskCancelledError`` stops
        whatever the engine was doing with it.
        """

        written = self.store.update_task_engine_state(
            task, include_definition=include_definition
        )
        if written is None:
            self.store.save_task(task)
        elif written is False:
            raise TaskCancelledError(task.id)

    def _adopt_operator_changes(self, task: Task) -> Task:
        """Refresh the fields an operator owns from the store, in place.

        The engine keeps one task object for a whole workflow. Between steps
        it picks up what a person changed (wording, criteria, priority,
        dependencies, overrides) so the next prompt and model choice use it,
        and it returns the stored row so the caller can see a status change.
        """

        fresh = self.store.get_task(task.id)
        if fresh is None:
            raise OrchestratorError(f"Task {task.id!r} disappeared during execution.")
        for name in (
            "title",
            "description",
            "acceptance_criteria",
            "task_type",
            "priority",
            "order_index",
            "depends_on_task_ids",
            "executor_overrides",
            "complexity",
            "sprint_id",
        ):
            setattr(task, name, getattr(fresh, name))
        return fresh

    def _acquire_task_lease(self, task: Task, project: Project) -> str | None:
        """Acquire a lease on a task. Returns the lease token or None if denied."""
        token = generate_lease_token()
        lease = self.store.acquire_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=task.id,
            holder_id=self.holder_id,
            lease_token=token,
        )
        if lease is None:
            return None
        self._task_lease_tokens[task.id] = token
        return token

    def _start_task_lease_heartbeat(self, task: Task, project: Project, token: str) -> None:
        """Renew the lease on a timer while this engine works on the task.

        ``run_task`` starts the timer and stops it when it returns or raises,
        so the timer never outlives the work it vouches for. A step is not
        obliged to produce output, and a built-in step produces none the
        orchestrator sees, so renewal cannot depend on step activity.
        An in-memory database has one connection and no second process to
        defend against; it gets no heartbeat thread.
        """

        previous = self._task_lease_heartbeats.pop(task.id, None)
        if previous is not None:
            previous.stop()
        if self.store.db_path == ":memory:" or self._TASK_LEASE_HEARTBEAT_SECONDS <= 0:
            return
        heartbeat = TaskLeaseHeartbeat(
            db_path=self.store.db_path,
            project_id=project.id,
            task_id=task.id,
            holder_id=self.holder_id,
            lease_token=token,
            interval_seconds=self._TASK_LEASE_HEARTBEAT_SECONDS,
        )
        heartbeat.start()
        self._task_lease_heartbeats[task.id] = heartbeat

    def _stop_task_lease_heartbeat(self, task_id: str) -> bool:
        """Stop the timer for one task. Returns whether one was running."""

        heartbeat = self._task_lease_heartbeats.pop(task_id, None)
        if heartbeat is None:
            return False
        heartbeat.stop()
        return True

    def _forget_task_lease(self, task_id: str) -> str | None:
        """Stop heartbeating a task and drop its token without releasing it."""

        self._stop_task_lease_heartbeat(task_id)
        return self._task_lease_tokens.pop(task_id, None)

    def close(self) -> None:
        """Stop every lease heartbeat this orchestrator started.

        Leases whose tokens are still held are left to expire on their own,
        which is what a crashed engine's leases do.
        """

        for task_id in list(self._task_lease_heartbeats):
            self._stop_task_lease_heartbeat(task_id)

    def _release_task_lease(self, task: Task, project: Project) -> None:
        """Release the lease on a task if held by this orchestrator."""
        token = self._forget_task_lease(task.id)
        if token is not None:
            self.store.release_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
                holder_id=self.holder_id,
                lease_token=token,
            )

    def _renew_task_lease(self, task: Task, project: Project) -> bool:
        """Renew the lease on a task held by this orchestrator.

        Returns True when renewed, False when this orchestrator holds no
        token for the task. Raises ``LeaseLostError`` when the token exists
        but the store refuses the renewal, meaning the lease expired or was
        taken over: continuing would race the new holder in the same checkout.
        """
        token = self._task_lease_tokens.get(task.id)
        if token is None:
            return False
        renewed = self.store.renew_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=task.id,
            holder_id=self.holder_id,
            lease_token=token,
        )
        if renewed is None:
            self._forget_task_lease(task.id)
            raise LeaseLostError(
                f"Lease on task {task.id!r} was lost (expired or taken over by another "
                "engine). Stopping this engine without touching the task."
            )
        return True

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
            self.prune_old_history(project, settings=settings)
            self.recover_orphaned_tasks(project.id)

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
            if self._acquire_task_lease(task, project) is None:
                raise OrchestratorError(
                    f"Task {task_id!r} is already leased by another orchestrator."
                )
            try:
                completed = self._run_task_isolated(project, workflow, task)
            except QuotaPauseError as exc:
                return self._quota_run_result(project, exc, executed_task_ids, blocked_task_ids)
            executed_task_ids.append(completed.id)
            if completed.status == "blocked":
                blocked_task_ids.append(completed.id)
            return ProjectRunResult(
                project_id=project.id,
                executed_task_ids=tuple(executed_task_ids),
                blocked_task_ids=tuple(blocked_task_ids),
                stop_reason="task_complete",
            )

        self._activate_first_planned_sprint(project.id)
        stop_reason = "idle"
        while True:
            task = self.select_next_task(project)
            if task is not None:
                try:
                    completed = self._run_task_isolated(project, workflow, task)
                except QuotaPauseError as exc:
                    return self._quota_run_result(
                        project, exc, executed_task_ids, blocked_task_ids
                    )
                executed_task_ids.append(completed.id)
                if completed.status == "blocked":
                    blocked_task_ids.append(completed.id)
                continue

            # No runnable task — check sprint state.
            sprint = self.store.get_active_sprint(project.id)
            if sprint is not None and self._sprint_fully_resolved(sprint):
                result = self._advance_sprint(project, sprint)
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

    def _quota_run_result(
        self,
        project: Project,
        exc: QuotaPauseError,
        executed_task_ids: list[str],
        blocked_task_ids: list[str],
    ) -> ProjectRunResult:
        """Summarize a pass that stopped because the backend quota ran out."""

        executed_task_ids.append(exc.task_id)
        return ProjectRunResult(
            project_id=project.id,
            executed_task_ids=tuple(executed_task_ids),
            blocked_task_ids=tuple(blocked_task_ids),
            stop_reason="quota_exhausted",
            retry_after=exc.retry_after,
            detail=exc.detail,
        )

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
        self._save_task(task)
        self._emit_event(
            run,
            "engine.quota_exhausted",
            {
                "step": step,
                "role_id": run.role_id,
                "retry_after": result.retry_after,
                "error": result.detail,
            },
        )
        self._release_task_lease(task, project)

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
            self._release_task_lease(task, project)

        workflow_step = task.workflow_current_step or "orchestrator"
        if task.status not in {"done", "cancelled"}:
            task.status = "blocked"
            task.blocked_reason = reason
            self._save_task(task)
        self._create_system_run(
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
            self._release_task_lease(task, project)

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
            self._release_task_lease(task, project)
        if task.status in {"done", "cancelled"}:
            return task
        task.status = "blocked"
        task.blocked_reason = reason
        self._save_task(task)
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
            task = self._select_project_system_task(project_id)
        if task is None:
            return None
        run = self._create_system_run(
            task,
            workflow_step=task.workflow_current_step or workflow_step,
            outcome=outcome,
            detail=detail,
        )
        return self._emit_event(run, event_type, payload)

    def _activate_first_planned_sprint(self, project_id: str) -> Sprint | None:
        """Activate the first planned sprint when project-scoped execution starts idle."""

        active = self.store.get_active_sprint(project_id)
        if active is not None:
            return active

        next_sprint = self.store.get_next_planned_sprint(project_id)
        if next_sprint is None:
            return None

        next_sprint.status = "active"
        next_sprint.started_at = next_sprint.started_at or self.utc_now().isoformat()
        next_sprint.completed_at = None
        self.store.save_sprint(next_sprint)
        return next_sprint

    def build_completion_evidence(
        self,
        task: Task,
        project: Project,
    ) -> CompletionEvidence | None:
        """Build structured completion evidence for one task.

        Records facts and nothing derived from them by weighting: which
        commit is the branch head, whether the test step passed and on which
        commit, what each reviewer decided and on which commit, and what a
        judge model said about each acceptance criterion when one is
        configured. ``proof_status`` is ``passed`` only when the tests passed
        on the head commit and the criteria were either all passed by a judge
        or covered by an approving code review of the head commit (ADR-0018).
        """
        runs = self.store.list_runs(task_id=task.id)

        # Git positional reference
        base_sha = ""
        head_sha_val = ""
        merge_base_sha_val = ""
        commit_count = 0
        try:
            base_sha = head_sha(project.repo_path, f"refs/heads/{project.default_branch}") or ""
            if task.branch_name:
                head_sha_val = head_sha(project.repo_path, f"refs/heads/{task.branch_name}") or ""
                merge_base_result = subprocess.run(
                    ["git", "merge-base", project.default_branch, task.branch_name],
                    cwd=project.repo_path,
                    capture_output=True,
                    text=True,
                )
                merge_base_sha_val = merge_base_result.stdout.strip()
                commit_count_result = subprocess.run(
                    ["git", "rev-list", "--count", f"{project.default_branch}..{task.branch_name}"],
                    cwd=project.repo_path,
                    capture_output=True,
                    text=True,
                )
                if commit_count_result.returncode == 0:
                    commit_count = int(commit_count_result.stdout.strip())
        except (FileNotFoundError, GitError, OSError, ValueError):
            pass

        # Changed files from git diff
        changed_files: tuple[str, ...] = ()
        diff_context_lines = 0
        branch_diff_stat = ""
        if task.branch_name:
            diff_text = self._safe_branch_diff(
                project.repo_path,
                project.default_branch,
                task.branch_name,
            )
            if diff_text:
                changed_files, diff_context_lines, branch_diff_stat = self._parse_diff_stats(
                    diff_text,
                )

        # Agent output summaries
        agent_outputs = self._collect_agent_outputs(runs)

        # Built-in test results
        test_events = [
            event
            for event in self.store.list_events(task_id=task.id)
            if event.event_type in ("engine.test_run", "engine.test_output")
        ]
        builtin_test_passed = False
        builtin_test_result = ""
        builtin_test_detail = ""
        test_exit_code: int | None = None
        tested_sha = ""
        test_duration_seconds: float | None = None
        for event in sorted(test_events, key=lambda e: e.timestamp):
            payload = event.payload
            if event.event_type == "engine.test_run":
                builtin_test_result = payload.get("command", "")
                test_exit_code = payload.get("exit_code")
                builtin_test_passed = test_exit_code == 0
                tested_sha = str(payload.get("head_sha") or "")
                duration = payload.get("duration_seconds")
                test_duration_seconds = (
                    float(duration) if isinstance(duration, (int, float)) else None
                )
            elif event.event_type == "engine.test_output":
                if payload.get("exit_code") == 0:
                    builtin_test_passed = True
                builtin_test_detail = payload.get("output", "")

        # A test run on a commit that is no longer the branch head says
        # nothing about the head. Runs recorded before the commit was captured
        # carry no SHA and are taken at face value.
        if not builtin_test_result:
            tests_status = "not_run"
        elif tested_sha and head_sha_val and tested_sha != head_sha_val:
            tests_status = "stale"
        else:
            tests_status = "passed" if builtin_test_passed else "failed"

        # Reviewer outcomes from completed decision-role runs. Roles declare
        # whether their decision is a code review or a security review, so any
        # reviewer (triage, frontier, a custom QA role) counts by contract.
        review_outcome = ""
        reviewed_sha = ""
        security_review_outcome = ""
        security_reviewed_sha = ""
        reviewed_sha_by_run = {
            event.run_id: str(event.payload.get("head_sha") or "")
            for event in self.store.list_events(task_id=task.id)
            if event.event_type == "engine.review_recorded"
        }
        review_kind_by_role = {
            role_id: role.completion.review_kind
            for role_id, role in self.roles.items()
            if role.completion.output.extract_decision
        }
        reviewer_runs = [
            r for r in runs
            if r.status == "completed" and r.role_id in review_kind_by_role
        ]
        for run in sorted(reviewer_runs, key=lambda r: r.completed_at or "", reverse=True):
            kind = review_kind_by_role[run.role_id]
            if kind == "code" and not review_outcome:
                review_outcome = run.outcome or ""
                reviewed_sha = reviewed_sha_by_run.get(run.id, "")
            if kind == "security" and not security_review_outcome:
                security_review_outcome = run.outcome or ""
                security_reviewed_sha = reviewed_sha_by_run.get(run.id, "")

        # Criteria coverage
        criteria_count = 0
        criteria_addressed = 0
        criteria_partially_addressed = 0
        criteria_text = task.acceptance_criteria or ""
        criteria_list = [c.strip() for c in criteria_text.split("\n") if c.strip()]
        criteria_count = len(criteria_list)
        criteria_checklist: list[dict[str, str]] = []
        judged_by = NOT_JUDGED

        if criteria_list:
            all_output_text = "\n".join(agent_outputs).lower()
            judge_diff = self._safe_branch_diff_content(
                project.repo_path,
                project.default_branch,
                task.branch_name,
            ) if task.branch_name else ""
            judgment = judge_criteria(
                criteria=criteria_list,
                diff_text=judge_diff,
                agent_summary=all_output_text,
                changed_files=changed_files,
                settings=project.settings,
            )
            judged_by = judgment.judged_by
            criteria_checklist = [dict(item) for item in judgment.checklist]
            criteria_addressed = sum(
                1 for item in criteria_checklist if item.get("status") == "passed"
            )
            criteria_partially_addressed = sum(
                1 for item in criteria_checklist if item.get("status") == "partial"
            )

        judged = judged_by != NOT_JUDGED
        review_approved = review_outcome == "approve"
        failure_reasons: list[str] = []
        outstanding: list[str] = []

        if tests_status == "failed":
            failure_reasons.append(f"Tests failed (exit code {test_exit_code}).")
        elif tests_status == "stale":
            failure_reasons.append(
                f"Tests ran on {tested_sha[:8]}; the branch is now at {head_sha_val[:8]}."
            )
        elif tests_status == "not_run":
            outstanding.append("Tests have not run.")

        review_is_stale = bool(
            review_approved and reviewed_sha and head_sha_val and reviewed_sha != head_sha_val
        )
        if review_is_stale:
            failure_reasons.append(
                f"Code review approved {reviewed_sha[:8]}; the branch is now at "
                f"{head_sha_val[:8]}."
            )

        # An approving code review covers the acceptance criteria. Without one,
        # only a judge model's "passed" on every criterion does; a criterion no
        # judge looked at is not counted as met.
        if criteria_checklist and not review_approved:
            if judged:
                for item in criteria_checklist:
                    if item.get("status") != "passed":
                        failure_reasons.append(
                            f"Criterion not fully addressed: {item.get('criterion', '')!r} "
                            f"({item.get('status')})."
                        )
            else:
                outstanding.append(
                    "Acceptance criteria were not checked by a judge model and code "
                    "review has not approved."
                )
        # Implementation tasks require acceptance criteria
        if task.task_type in {"feature", "fix", "refactor"} and not criteria_checklist:
            failure_reasons.append("No acceptance criteria defined.")

        if failure_reasons:
            proof_status = "failed"
        elif outstanding:
            proof_status = "pending"
        else:
            proof_status = "passed"

        return CompletionEvidence(
            task_id=task.id,
            task_title=task.title,
            acceptance_criteria=criteria_text,
            criteria_count=criteria_count,
            criteria_addressed=criteria_addressed,
            criteria_partially_addressed=criteria_partially_addressed,
            changed_files=changed_files,
            diff_context_lines=diff_context_lines,
            branch_diff_stat=branch_diff_stat,
            agent_outputs=agent_outputs,
            builtin_test_result=builtin_test_result,
            builtin_test_passed=builtin_test_passed,
            builtin_test_detail=builtin_test_detail,
            base_sha=base_sha,
            head_sha=head_sha_val,
            merge_base_sha=merge_base_sha_val,
            commit_count=commit_count,
            test_command=builtin_test_result,
            test_exit_code=test_exit_code,
            tests_status=tests_status,
            tested_sha=tested_sha,
            test_duration_seconds=test_duration_seconds,
            review_outcome=review_outcome,
            reviewed_sha=reviewed_sha,
            security_review_outcome=security_review_outcome,
            security_reviewed_sha=security_reviewed_sha,
            criteria_checklist=tuple(criteria_checklist),
            proof_status=proof_status,
            failure_reasons=tuple(failure_reasons),
            outstanding=tuple(outstanding),
            judged_by=judged_by,
        )

    def _safe_branch_diff(
        self,
        repo_path: str,
        target_branch: str,
        branch_name: str,
    ) -> str:
        """Return ``git diff --numstat -z`` output for one branch, or an empty
        string on failure."""
        for rev_args in (
            [f"{target_branch}...{branch_name}"],
            [target_branch, branch_name],
        ):
            try:
                result = subprocess.run(
                    ["git", "diff", "--numstat", "-z", *rev_args],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="surrogateescape",
                    check=False,
                )
                if result.returncode == 0:
                    return result.stdout
            except Exception:  # pragma: no cover
                pass
        return ""

    def _parse_diff_stats(
        self,
        diff_output: str,
    ) -> tuple[tuple[str, ...], int, str]:
        """Parse ``git diff --numstat -z`` output into structured fields.

        Returns ``(changed_files, changed_file_count, summary_line)``. The
        integer is the number of changed files. The summary has the form
        ``"N file(s), +A, -D"``. Binary files (``-`` counts) are listed with 0
        added and 0 deleted. A rename is listed under its new path. Paths are
        used exactly as git reports them.
        """
        tokens = diff_output.split("\0")
        changed_files: list[str] = []
        total_additions = 0
        total_deletions = 0
        i = 0
        while i < len(tokens):
            token = tokens[i]
            i += 1
            if not token:
                continue
            parts = token.split("\t", 2)
            if len(parts) != 3:
                continue
            added, deleted, path = parts
            if path == "":
                # Rename/copy: the old and new paths follow as separate records.
                path = tokens[i + 1] if i + 1 < len(tokens) else ""
                i += 2
                if not path:
                    continue
            changed_files.append(path)
            if added.isdigit():
                total_additions += int(added)
            if deleted.isdigit():
                total_deletions += int(deleted)

        summary = f"{len(changed_files)} file(s), +{total_additions}, -{total_deletions}"
        return (tuple(changed_files), len(changed_files), summary)

    def _collect_agent_outputs(self, runs: list[Run]) -> tuple[str, ...]:
        """Extract meaningful output snippets from completed agent runs."""
        outputs: list[str] = []
        for run in runs:
            if run.status not in {"completed", "failed", "killed", "timeout"}:
                continue
            detail = run.outcome_detail or ""
            # Capture first meaningful chunk of output (up to 500 chars)
            snippet = detail[:500].strip() if detail.strip() else ""
            if snippet:
                role_and_step = f"[{run.role_id} / {run.workflow_step}]"
                outputs.append(f"{role_and_step}: {snippet}")
        return tuple(outputs)

    def _safe_branch_diff_content(
        self,
        repo_path: str,
        target_branch: str,
        branch_name: str,
        *,
        max_chars: int = 24000,
    ) -> str:
        """Return unified ``git diff`` content for one branch, head+tail capped
        to ``max_chars``, or empty string on failure."""
        for diff_args in (
            ["git", "diff", f"{target_branch}...{branch_name}"],
            ["git", "diff", target_branch, branch_name],
        ):
            try:
                result = subprocess.run(
                    diff_args,
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception:  # pragma: no cover - defensive
                continue
            if result.returncode == 0 and result.stdout:
                return truncate_diff(result.stdout, max_chars)
        return ""


    def select_next_task(self, project: Project) -> Task | None:
        """Return the next runnable task for one project."""

        selection_mode = str(project.settings.get("task_selection_mode", "directed"))
        if selection_mode == "autonomous":
            return self._select_next_task_autonomous(project)
        if selection_mode != "directed":
            raise OrchestratorError(
                f"Task selection mode {selection_mode!r} is not implemented."
            )

        sprint = self.store.get_active_sprint(project.id)
        if sprint is None:
            return None
        sprint_tasks = self.store.list_tasks(sprint_id=sprint.id)
        tasks_by_id = {task.id: task for task in sprint_tasks}
        for task in sprint_tasks:
            if task.status == "in_progress" and task.workflow_current_step:
                # For resumption, try to acquire the lease. If the old holder is
                # still alive (lease not expired), skip this task to avoid stealing
                # work. If the lease has expired, we take it over.
                if self._acquire_task_lease(task, project) is None:
                    return None  # Another orchestrator holds an active lease.
                return task
        if any(
            task.status == "in_progress" and not task.workflow_current_step
            for task in sprint_tasks
        ):
            return None
        for task in sprint_tasks:
            if task.status != "todo":
                continue
            cancelled = self._cancelled_dependencies(task, tasks_by_id)
            if cancelled:
                # The prerequisite will never be delivered. Running the task
                # anyway would build on work that does not exist; park it for
                # a person to re-plan instead.
                self.block_task_for_error(
                    task.id,
                    "Dependency cancelled: "
                    + ", ".join(cancelled)
                    + ". Re-plan the task, then `foreman task unblock` it or cancel it.",
                    attention_trigger="dependency_cancelled",
                )
                continue
            if not self._dependencies_satisfied(task, tasks_by_id):
                continue
            # Lease the task before returning it. If denied, another
            # orchestrator holds it — skip to the next candidate.
            if self._acquire_task_lease(task, project) is None:
                continue
            return task
        return None

    _MAX_AUTONOMOUS_TASKS_DEFAULT = 5

    def _select_next_task_autonomous(self, project: Project) -> Task | None:
        """Select the next task in autonomous mode.

        Resumes an in-progress task if one exists.  Otherwise creates a new
        placeholder task for the agent to populate via ``signal.task_started``.
        Returns ``None`` when there is no active sprint or the autonomous task
        limit for this sprint has been reached.
        """
        sprint = self.store.get_active_sprint(project.id)
        if sprint is None:
            return None

        sprint_tasks = self.store.list_tasks(sprint_id=sprint.id)

        # Resume an in-progress task that has a persisted workflow position.
        for task in sprint_tasks:
            if task.status == "in_progress" and task.workflow_current_step:
                # For resumption, try to acquire the lease. If the old holder is
                # still alive (lease not expired), skip this task to avoid
                # stealing work. If the lease has expired, we take it over.
                if self._acquire_task_lease(task, project) is None:
                    return None  # Another orchestrator holds an active lease.
                return task
        if any(
            task.status == "in_progress" and not task.workflow_current_step
            for task in sprint_tasks
        ):
            return None

        # Check the per-sprint autonomous task limit.
        max_tasks = int(
            project.settings.get("max_autonomous_tasks", self._MAX_AUTONOMOUS_TASKS_DEFAULT)
        )
        orchestrator_tasks = [t for t in sprint_tasks if t.created_by == "orchestrator"]
        if len(orchestrator_tasks) >= max_tasks:
            return None

        # Create a new placeholder task for the agent to populate.
        placeholder = Task(
            id=str(uuid4()),
            sprint_id=sprint.id,
            project_id=project.id,
            title="[autonomous] new task",
            status="todo",
            created_by="orchestrator",
        )
        self._save_task(placeholder)
        # Acquire lease for the new placeholder immediately.
        if self._acquire_task_lease(placeholder, project) is None:
            # Race: another orchestrator created one first; reload and return it.
            sprint_tasks = self.store.list_tasks(sprint_id=sprint.id)
            for task in sprint_tasks:
                if task.status == "in_progress" and task.workflow_current_step:
                    return task
            return None
        return placeholder

    def run_task(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
    ) -> Task:
        """Run one task from the workflow entry step, heartbeating its lease throughout."""

        token = self._task_lease_tokens.get(task.id)
        if token is not None:
            self._start_task_lease_heartbeat(task, project, token)
        try:
            return self._run_leased_task(project, workflow, task)
        finally:
            self._stop_task_lease_heartbeat(task.id)

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
                run for run in active_runs if self._run_is_stale(project, run)
            ]
            if recoverable_runs:
                self._recover_stale_running_runs(project, current_task, recoverable_runs)
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

        if str(project.settings.get("task_selection_mode", "directed")) == "directed":
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
        self._save_task(current_task)

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
                    mirror_dirs=self._context_mirror_dirs(project, refreshed),
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
        decision_run = self._create_system_run(
            current_task,
            workflow_step=paused_step.id,
            outcome=outcome,
            detail=decision_detail,
            role_id="_builtin:human_gate",
            agent_backend="human",
        )
        self._emit_event(
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
        self._emit_event(
            decision_run,
            "workflow.resumed",
            event_payload,
        )

        # Persist human gate decision as a durable audit record
        human_decision = HumanGateDecision(
            id=_new_id("hg"),
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
        self._save_task(current_task)

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

        if str(project.settings.get("task_selection_mode", "directed")) == "directed":
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
                    mirror_dirs=self._context_mirror_dirs(project, refreshed),
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
            self._complete_run(
                run,
                status="failed",
                outcome=ERROR,
                detail=detail,
                session_id=self._session_id_from_events(run) or run.session_id,
                failure_type="infrastructure",
            )

    def _abandon_cancelled_task(self, project: Project, task: Task) -> Task:
        """Close the engine's open work on a task an operator cancelled."""

        for run in self.store.list_runs(task_id=task.id):
            if run.status == "running":
                self._complete_run(
                    run,
                    status="killed",
                    outcome=ERROR,
                    detail="Task was cancelled while this step was running.",
                    session_id=run.session_id,
                )
        self._release_task_lease(task, project)
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
            stored = self._adopt_operator_changes(current_task)
            if stored.status == "cancelled":
                raise TaskCancelledError(current_task.id)
            if stored.status == "blocked":
                current_task.status = stored.status
                current_task.blocked_reason = stored.blocked_reason
                self._release_task_lease(current_task, project)
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
                        run = self._create_system_run(
                            current_task,
                            workflow_step=current_step,
                            outcome="blocked",
                            detail=str(e),
                        )
                        self._emit_event(
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
                        self._save_task(current_task)
                        current_step = None
                        self._release_task_lease(current_task, project)
                        break

            # ── Autonomous contract: require signal.task_started after first developer step ──
            # Pre-step check only for non-developer steps; developer step is checked
            # after execution so the agent has a chance to emit signal.task_started.
            mode = str(project.settings.get("task_selection_mode", "directed"))
            if mode == "autonomous" and current_task.created_by == "orchestrator":
                if current_task.id not in self._task_started_received:
                    if step_def.role not in {"_builtin:merge", "_builtin:mark_done", "developer"}:
                        detail = (
                            "Autonomous task did not emit required signal.task_started. "
                            "Missing: title, branch, or acceptance_criteria."
                        )
                        run = self._create_system_run(
                            current_task,
                            workflow_step=current_step,
                            outcome="blocked",
                            detail=detail,
                        )
                        self._emit_event(
                            run,
                            "workflow.autonomous_contract_missing",
                            {
                                "task_id": current_task.id,
                                "step": current_step,
                                "reason": detail,
                            },
                        )
                        current_task.status = "blocked"
                        current_task.blocked_reason = detail
                        self._save_task(current_task)
                        current_step = None
                        self._release_task_lease(current_task, project)
                        break

            visit_count = current_task.step_visit_counts.get(current_step, 0) + 1
            current_task.step_visit_counts[current_step] = visit_count
            self._save_task(current_task)

            max_step_visits = _int_setting(project, "max_step_visits", default=5)
            if visit_count > max_step_visits:
                detail = (
                    f"Step '{current_step}' visited {visit_count} times "
                    f"(limit: {max_step_visits}). Stuck in a loop."
                )
                run = self._create_system_run(
                    current_task,
                    workflow_step=current_step,
                    outcome="blocked",
                    detail=detail,
                    attention_trigger="loop_limit",
                )
                self._emit_event(
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
                self._save_task(current_task)
                break

            task_cost = sum(run.cost_usd for run in self.store.list_runs(task_id=current_task.id))
            cost_limit = _float_setting(
                project,
                "cost_limit_per_task_usd",
                default=None,
            )
            # 0 is the documented "off" value, and what the settings screen saves.
            if cost_limit is not None and cost_limit > 0 and task_cost >= cost_limit:
                detail = f"Task cost ${task_cost:.2f} exceeds limit ${cost_limit:.2f}"
                run = self._create_system_run(
                    current_task,
                    workflow_step=current_step,
                    outcome="blocked",
                    detail=detail,
                )
                self._emit_event(
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
                self._save_task(current_task)
                break

            sprint_cost_limit = _float_setting(
                project,
                "cost_limit_per_sprint_usd",
                default=None,
            )
            sprint_cost = float(
                self.store.run_totals(sprint_id=current_task.sprint_id)["total_cost_usd"]
            )
            if (
                sprint_cost_limit is not None
                and sprint_cost_limit > 0
                and sprint_cost >= sprint_cost_limit
            ):
                detail = (
                    f"Sprint cost ${sprint_cost:.2f} exceeds limit "
                    f"${sprint_cost_limit:.2f}"
                )
                run = self._create_system_run(
                    current_task,
                    workflow_step=current_step,
                    outcome="blocked",
                    detail=detail,
                )
                self._emit_event(
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
                self._save_task(current_task)
                break

            task_duration_ms = sum(
                run.duration_ms or 0
                for run in self.store.list_runs(task_id=current_task.id)
            )
            time_limit_ms = _int_setting(
                project,
                "time_limit_per_task_ms",
                default=0,
            )
            if time_limit_ms > 0 and task_duration_ms >= time_limit_ms:
                detail = f"Task time {task_duration_ms/1000:.1f}s exceeds limit {time_limit_ms/1000:.1f}s"
                run = self._create_system_run(
                    current_task,
                    workflow_step=current_step,
                    outcome="blocked",
                    detail=detail,
                )
                self._emit_event(
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
                self._save_task(current_task)
                break

            branch_sync_event: tuple[str, dict[str, Any]] | None = None
            if current_task.branch_name and step_def.role not in {
                "_builtin:merge",
                "_builtin:mark_done",
            }:
                (
                    carried_output,
                    branch_sync_event,
                ) = self._prepare_task_branch_for_step(
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
            self._save_task(current_task)

            # Poll *after* the resume point is persisted: an interrupt here
            # must leave the task resumable at the step it was about to run,
            # not at the one it already finished.
            self._poll_commands(current_task.id)

            if step_def.role == "_builtin:human_gate":
                run = self._create_running_run(
                    current_task,
                    role_id=step_def.role,
                    workflow_step=current_step,
                    agent_backend="builtin",
                )
                self._emit_event(
                    run,
                    "workflow.step_started",
                    {"step": current_step, "visit_count": visit_count},
                )
                self._emit_policy_resolved(run, project, current_task)
                gate_policy = self._gate_policy_decision(project, current_task, step_def)
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
                        working_dir=self._task_working_dir(project, current_task),
                    )
                    self._save_task(current_task)
                    self._complete_run(
                        run,
                        status="completed",
                        outcome=result.outcome,
                        detail=result.detail,
                    )
                    self._emit_builtin_events(run, result.events)
                    self._emit_event(
                        run,
                        "workflow.paused",
                        {
                            "step": current_step,
                            "reason": "human_gate",
                            "policy": step_def.policy,
                            # What the project asked to be told about; the
                            # delivery worker acts on this persisted decision.
                            "notify": self._notification_policy(project, current_task),
                        },
                    )
                    # A task waiting for a person is not being worked on. Left
                    # held, the lease made the engine wait out its remaining
                    # lifetime before it could act on the decision.
                    self._release_task_lease(current_task, project)
                    return current_task

            elif step_def.role.startswith("_builtin:"):
                run = self._create_running_run(
                    current_task,
                    role_id=step_def.role,
                    workflow_step=current_step,
                    agent_backend="builtin",
                )
                self._emit_event(
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
                    working_dir=self._task_working_dir(project, current_task),
                )
                self._save_task(current_task)
                self._complete_run(
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
                    self._emit_attention_needed(
                        run,
                        current_task.id,
                        self._attention_trigger_for_block(current_task),
                    )
                outcome = normalize_agent_outcome(result.outcome)
                detail = result.detail
            else:
                role = self.roles.get(step_def.role)
                if role is None:
                    raise OrchestratorError(f"Unknown role {step_def.role!r}.")
                current_task.assigned_role = role.id
                self._save_task(current_task)

                context_projection = build_project_context(
                    self.store,
                    project,
                    current_task=current_task,
                    carried_output=carried_output,
                    mirror_dirs=self._context_mirror_dirs(project, current_task),
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
                run = self._create_running_run(
                    current_task,
                    role_id=role.id,
                    workflow_step=current_step,
                    agent_backend=role.agent.backend,
                    model=model_selection.model,
                    branch_name=current_task.branch_name,
                    prompt_text=prompt,
                )
                self._emit_event(
                    run,
                    "workflow.model_selected",
                    {
                        "step": current_step,
                        "model": model_selection.model,
                        "visit_count": visit_count,
                        "source": model_selection.source,
                    },
                )
                self._emit_event(
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
                self._emit_event(
                    run,
                    "agent.prompt",
                    {"text": prompt},
                    role_id=role.id,
                )
                if guidance:
                    self._emit_event(
                        run,
                        GUIDANCE_DELIVERED_EVENT,
                        {
                            "message_event_ids": [note.event_id for note in guidance],
                            "role": role.id,
                            "step": current_step,
                        },
                    )
                self._emit_event(
                    run,
                    "workflow.step_started",
                    {"step": current_step, "visit_count": visit_count},
                )
                self._emit_policy_resolved(run, project, current_task)
                if branch_sync_event is not None:
                    event_type, payload = branch_sync_event
                    self._emit_event(run, event_type, payload)
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
                result = self._execute_agent_step_guarded(
                    run=run,
                    role=role,
                    project=project,
                    task=current_task,
                    workflow_step=current_step,
                    prompt=prompt,
                    session_id=session_id,
                    carried_output=carried_output,
                    model=model_selection.model,
                    event_recorder=lambda event_record: self._persist_agent_event(
                        run,
                        current_task,
                        project,
                        role.id,
                        event_record,
                    ),
                )
                if not result.events_streamed:
                    self._emit_agent_events(run, current_task, project, role.id, result.events)
                self._complete_run(
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
                    else self._output_contract_retry_reason(role, result)
                )
                if retry_reason is not None:
                    self._emit_event(
                        run,
                        "engine.output_contract_retry",
                        {
                            "step": current_step,
                            "role_id": role.id,
                            "reason": retry_reason,
                            "retry_attempt": 1,
                        },
                    )
                    retry_prompt = self._append_output_contract_retry_instruction(
                        prompt,
                        role,
                        retry_reason,
                    )
                    retry_session_id = result.session_id or session_id
                    retry_run = self._create_running_run(
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
                    self._emit_event(
                        retry_run,
                        "workflow.step_started",
                        {
                            "step": current_step,
                            "visit_count": visit_count,
                            "retry_attempt": 1,
                        },
                    )
                    retry_result = self._execute_agent_step_guarded(
                        run=retry_run,
                        role=role,
                        project=project,
                        task=current_task,
                        workflow_step=current_step,
                        prompt=retry_prompt,
                        session_id=retry_session_id,
                        carried_output=carried_output,
                        model=model_selection.model,
                        event_recorder=lambda event_record: self._persist_agent_event(
                            retry_run,
                            current_task,
                            project,
                            role.id,
                            event_record,
                        ),
                    )
                    if not retry_result.events_streamed:
                        self._emit_agent_events(
                            retry_run,
                            current_task,
                            project,
                            role.id,
                            retry_result.events,
                        )
                    self._complete_run(
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
                    self._emit_event(
                        run,
                        "engine.review_recorded",
                        {
                            "role": role.id,
                            "review_kind": role.completion.review_kind,
                            "outcome": outcome,
                            "head_sha": self._safe_branch_head(project, current_task),
                        },
                    )
                else:
                    outcome = normalize_agent_outcome(result.outcome)
                detail = result.detail

            # ── Autonomous contract check: after developer step executes ──
            # Record that a developer step ran, then check whether signal was received.
            mode = str(project.settings.get("task_selection_mode", "directed"))
            if mode == "autonomous" and current_task.created_by == "orchestrator":
                if step_def.role == "developer":
                    self._developer_step_executed.add(current_task.id)
                if (
                    current_task.id in self._developer_step_executed
                    and current_task.id not in self._task_started_received
                ):
                    # Also accept persisted non-placeholder fields as valid signal substitute
                    has_persisted_signal = (
                        current_task.title
                        and current_task.title != "[autonomous] new task"
                        and current_task.branch_name
                        and current_task.acceptance_criteria
                    )
                    if not has_persisted_signal:
                        detail = (
                            "Autonomous task did not emit required signal.task_started "
                            "after the first developer step."
                        )
                        run = self._create_system_run(
                            current_task,
                            workflow_step=current_step,
                            outcome="blocked",
                            detail=detail,
                        )
                        self._emit_event(
                            run,
                            "workflow.autonomous_contract_missing",
                            {
                                "task_id": current_task.id,
                                "step": current_step,
                                "reason": detail,
                            },
                        )
                        current_task.status = "blocked"
                        current_task.blocked_reason = detail
                        self._save_task(current_task)
                        current_step = None
                        self._release_task_lease(current_task, project)
                        break

            self._emit_event(
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
                self._save_task(current_task)

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
                run = self._create_system_run(
                    current_task,
                    workflow_step=current_step,
                    outcome="blocked",
                    detail=detail,
                )
                self._emit_event(
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
                self._save_task(current_task)
                current_step = None
                self._release_task_lease(current_task, project)
                break

            transition = workflow.find_transition(current_step, outcome)
            if transition is None:
                if current_task.status == "done":
                    current_task.workflow_current_step = None
                    current_task.workflow_carried_output = None
                    self._save_task(current_task)
                    current_step = None
                    self._release_task_lease(current_task, project)
                    break

                self._emit_event(
                    run,
                    "workflow.no_transition",
                    {"step": current_step, "outcome": outcome},
                )
                current_task.status = "blocked"
                current_task.blocked_reason = self._blocked_reason_for_unhandled_outcome(
                    workflow=workflow,
                    step=current_step,
                    outcome=outcome,
                    detail=detail,
                )
                current_task.workflow_current_step = None
                current_task.workflow_carried_output = None
                self._save_task(current_task)
                current_step = None
                self._release_task_lease(current_task, project)
                continue

            self._emit_event(
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
                self._emit_event(
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
            self._save_task(current_task)
            current_step = transition.to_step

            # Renew lease after each step (heartbeat during workflow execution).
            if current_step is not None:
                self._renew_task_lease(current_task, project)

        # Every path that parks a task leaves it ``blocked``: a gate, a loop
        # or cost limit, a failed guard. A parked task is not being worked on,
        # so nothing may keep holding (and heartbeating) its lease.
        if current_task.status == "blocked":
            self._release_task_lease(current_task, project)

        return current_task

    def _gate_policy_decision(
        self,
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
        self._emit_event(
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
        self._emit_event(
            run,
            "workflow.gate_auto_approved",
            {"step": step.id, "policy": step.policy},
        )
        self._complete_run(run, status="completed", outcome=APPROVE, detail=detail)
        self.store.save_human_gate_decision(
            HumanGateDecision(
                id=_new_id("hg"),
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

    def _blocked_reason_for_unhandled_outcome(
        self,
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

    def recover_orphaned_tasks(self, project_id: str) -> None:
        """Reset orphaned in-progress tasks after a prior engine crash."""

        project = self.store.get_project(project_id)
        if project is None:
            return
        orphaned_tasks = self.store.list_tasks(project_id=project_id, status="in_progress")
        for task in orphaned_tasks:
            if task.workflow_current_step is not None:
                continue

            active_runs = self.store.list_runs(task_id=task.id, status="running")
            stale_runs = [run for run in active_runs if self._run_is_stale(project, run)]
            if active_runs and not stale_runs:
                continue

            if stale_runs:
                self._recover_stale_running_runs(project, task, stale_runs)
                continue

            if not active_runs:
                system_run = self._create_system_run(
                    task,
                    workflow_step=task.workflow_current_step or "orchestrator",
                    outcome="error",
                    detail="Recovered orphaned task without an active run.",
                )
                self._emit_event(
                    system_run,
                    "engine.crash_recovery",
                    {
                        "task_id": task.id,
                        "message": "Reset to todo after orphaned run.",
                    },
                )

            task.status = "todo"
            task.blocked_reason = None
            task.step_visit_counts = {}
            self._save_task(task)

    def _recover_stale_running_runs(
        self,
        project: Project,
        task: Task,
        runs: list[Run],
    ) -> None:
        """Fail stale running runs and reset task state so the slice can be retried safely."""

        now = utc_now_text()

        # Capture lease metadata for the recovery event.
        task_lease = self.store.get_active_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=task.id,
        )

        for run in runs:
            run.status = "failed"
            run.outcome = "error"
            run.outcome_detail = "Recovered stale running run after exceeding the active-run limit."
            run.completed_at = now
            self.store.save_run(run)
            self._emit_event(
                run,
                "engine.crash_recovery",
                {
                    "task_id": task.id,
                    "lease_id": task_lease.id if task_lease else None,
                    "holder_id": task_lease.holder_id if task_lease else None,
                    "fencing_token": task_lease.fencing_token if task_lease else None,
                    "message": "Marked stale running run as failed.",
                },
            )

        # Force-expire any active task lease for the recovered task so the
        # next orchestrator can acquire it immediately. Without this, a lease
        # whose `expires_at` is still in the future would block re-acquisition
        # even after the run is marked failed.
        # ``run_task`` reaches this holding the lease it has just acquired.
        # Expiring that one too made the very next renewal fail, so every
        # resume after a crash cost one wasted agent run. Clear what a dead
        # engine left, then hold the task again.
        held_by_us = task.id in self._task_lease_tokens
        heartbeating = task.id in self._task_lease_heartbeats
        if held_by_us:
            self._forget_task_lease(task.id)
        self.store.expire_resource_leases(
            project_id=project.id,
            resource_type="task",
            resource_id=task.id,
            force=True,
        )
        if held_by_us:
            token = self._acquire_task_lease(task, project)
            if token is None:
                raise LeaseLostError(
                    f"Lease on task {task.id!r} could not be re-acquired after stale-run recovery."
                )
            if heartbeating:
                self._start_task_lease_heartbeat(task, project, token)

        task.status = "todo"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.step_visit_counts = {}
        self._save_task(task)

    def _run_is_stale(self, project: Project, run: Run) -> bool:
        """Return whether a persisted running run has exceeded its allowed ownership window.

        A run is considered stale when:
        1. Its configured timeout has elapsed, AND
        2. The task's active lease is either missing, expired, or held by a
           holder whose heartbeat is older than the liveness threshold
           (meaning the original holder is gone and the lease is no longer
           being heartbeated).
        """

        timeout_seconds = _active_run_recovery_timeout_seconds(project)
        if timeout_seconds is None or timeout_seconds <= 0:
            return False

        # Check if the run's timeout has elapsed.
        reference = self.store.get_latest_event_timestamp(run.id) or run.started_at or run.created_at
        started = _parse_utc_timestamp(reference)
        if started is None:
            return False
        if (self.utc_now() - started).total_seconds() <= timeout_seconds:
            return False

        # Timeout has elapsed: expire any past-due leases for this task, then
        # check the liveness of the remaining lease by its heartbeat timestamp.
        # A lease whose heartbeat is stale is treated as if its holder is gone.
        self.store.expire_resource_leases(
            project_id=project.id,
            resource_type="task",
            resource_id=run.task_id,
        )
        task_lease = self.store.get_active_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=run.task_id,
        )
        if task_lease is not None and task_lease.holder_id != self.holder_id:
            if _is_lease_live(task_lease, self.utc_now(), self._LEASE_LIVENESS_THRESHOLD_SECONDS):
                # Another orchestrator is actively heartbeating, so not stale.
                return False

        return True

    def prune_old_history(
        self,
        project: Project,
        *,
        settings: ProjectSettings | None = None,
    ) -> dict[str, int]:
        """Prune old project history according to per-type retention settings.

        Reads three optional retention settings through the validated
        ``ProjectSettings`` model:

        - ``event_retention_days`` — hard-delete old events
        - ``run_retention_days`` — hard-delete old terminal runs and their events
        - ``prompt_retention_days`` — null out prompt_text on old terminal runs

        Each setting is independent and disabled when unset. Returns a dict
        with counts for each type that was actually pruned.
        """

        counts: dict[str, int] = {}
        if settings is None:
            settings = resolve_project_settings(project)

        event_days = settings.event_retention_days
        if event_days is not None:
            cutoff = self._retention_cutoff(event_days)
            n = self.store.prune_old_events(project_id=project.id, older_than=cutoff)
            if n > 0:
                counts["events"] = n
                self._emit_pruned_event(project, "engine.event_pruned", n, cutoff)

        run_days = settings.run_retention_days
        if run_days is not None:
            cutoff = self._retention_cutoff(run_days)
            n = self.store.prune_old_runs(project_id=project.id, older_than=cutoff)
            if n > 0:
                counts["runs"] = n
                self._emit_pruned_event(project, "engine.run_pruned", n, cutoff)

        prompt_days = settings.prompt_retention_days
        if prompt_days is not None:
            cutoff = self._retention_cutoff(prompt_days)
            n = self.store.strip_old_run_prompts(project_id=project.id, older_than=cutoff)
            if n > 0:
                counts["prompts"] = n
                self._emit_pruned_event(project, "engine.prompt_stripped", n, cutoff)

        return counts

    def _retention_cutoff(self, days: int) -> str:
        """Return an ISO 8601 UTC timestamp ``days`` before now."""

        return (
            self.utc_now() - timedelta(days=days)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _emit_pruned_event(
        self,
        project: Project,
        event_type: str,
        count: int,
        older_than: str,
    ) -> None:
        """Emit a project-scoped lifecycle event for a completed pruning operation."""

        task = self._select_project_system_task(project.id)
        if task is None:
            return
        run = self._create_system_run(
            task,
            workflow_step="orchestrator",
            outcome="success",
            detail=f"{event_type}: {count} rows older than {older_than}.",
        )
        self._emit_event(run, event_type, {"count": count, "older_than": older_than})

    # Keep the old name as a thin delegate so any existing call sites outside
    # this class continue to work during the transition period.
    def prune_old_events(self, project: Project) -> int:
        """Prune old project events only.  Prefer prune_old_history() for new code."""

        result = self.prune_old_history(project)
        return result.get("events", 0)

    def _select_project_system_task(self, project_id: str) -> Task | None:
        """Choose a stable task for project-scoped synthetic orchestrator events."""

        active_tasks = self.store.list_tasks(
            project_id=project_id,
            statuses=("in_progress", "blocked"),
        )
        if active_tasks:
            return active_tasks[0]

        active_sprint = self.store.get_active_sprint(project_id)
        if active_sprint is not None:
            sprint_tasks = self.store.list_tasks(sprint_id=active_sprint.id)
            if sprint_tasks:
                return sprint_tasks[0]

        project_tasks = self.store.list_tasks(project_id=project_id)
        return project_tasks[0] if project_tasks else None

    # ── Sprint advancement ────────────────────────────────────────────────────

    def _sprint_fully_resolved(self, sprint: Sprint) -> bool:
        """Return True when every task in the sprint is done or cancelled."""
        tasks = self.store.list_tasks(sprint_id=sprint.id)
        return bool(tasks) and all(t.status in {"done", "cancelled"} for t in tasks)

    def _advance_sprint(self, project: Project, sprint: Sprint) -> str | None:
        """Complete *sprint* and advance to the next planned sprint if appropriate.

        Returns:
            None            — autonomous mode advanced; caller should continue loop.
            "sprint_complete" — next sprint is queued but waiting for human.
            "idle"          — sprint done, no further sprints in the queue.
        """
        now = self.utc_now().isoformat()
        sprint.status = "completed"
        sprint.completed_at = now
        self.store.save_sprint(sprint)
        self._emit_sprint_event(project, "engine.sprint_completed", {
            "sprint_id": sprint.id,
            "sprint_title": sprint.title,
        }, sprint=sprint)

        next_sprint = self.store.get_next_planned_sprint(project.id)
        if next_sprint is None:
            # Work is exhausted; the manager may want to plan more.
            self._emit_sprint_attention(project, sprint)
            return "idle"

        if project.autonomy_level == "autonomous":
            next_sprint.status = "active"
            next_sprint.started_at = now
            self.store.save_sprint(next_sprint)
            self._emit_sprint_event(project, "engine.sprint_started", {
                "sprint_id": next_sprint.id,
                "sprint_title": next_sprint.title,
            }, sprint=next_sprint)
            return None  # continue loop

        # supervised or directed: emit ready signal and stop.
        if project.autonomy_level == "supervised":
            self._emit_sprint_event(project, "engine.sprint_ready", {
                "sprint_id": next_sprint.id,
                "sprint_title": next_sprint.title,
            }, sprint=sprint)
        # The engine stops here and hands the next move to the manager/human.
        self._emit_sprint_attention(project, sprint)
        return "sprint_complete"

    def _emit_sprint_event(
        self,
        project: Project,
        event_type: str,
        payload: dict[str, Any],
        *,
        sprint: Sprint,
    ) -> None:
        """Emit a sprint-scoped lifecycle event via a synthetic run."""
        tasks = self.store.list_tasks(sprint_id=sprint.id)
        task = tasks[0] if tasks else self._select_project_system_task(project.id)
        if task is None:
            return
        run = self._create_system_run(
            task, workflow_step="orchestrator", outcome="success", detail=event_type
        )
        self._emit_event(run, event_type, payload)

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

    def _dependencies_satisfied(
        self,
        task: Task,
        tasks_by_id: Mapping[str, Task],
    ) -> bool:
        for dependency_id in task.depends_on_task_ids:
            dependency = tasks_by_id.get(dependency_id) or self.store.get_task(dependency_id)
            if dependency is None:
                return False
            # Only a delivered dependency satisfies. A cancelled one is a
            # planning decision the dependent task must be re-planned around;
            # ``_cancelled_dependencies`` turns it into a block with attention.
            if dependency.status != "done":
                return False
        return True

    def _cancelled_dependencies(
        self,
        task: Task,
        tasks_by_id: Mapping[str, Task],
    ) -> list[str]:
        cancelled: list[str] = []
        for dependency_id in task.depends_on_task_ids:
            dependency = tasks_by_id.get(dependency_id) or self.store.get_task(dependency_id)
            if dependency is not None and dependency.status == "cancelled":
                cancelled.append(dependency.id)
        return cancelled

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
        if evidence is not None and self._completion_evidence_stale(evidence, task, project):
            evidence = None
            task.completion_evidence = None
        if evidence is None and role.completion.output.extract_decision:
            evidence = self.build_completion_evidence(task, project)
            task.completion_evidence = evidence
            self._save_task(task)
        context = {
            "task_title": task.title,
            "task_description": task.description or "",
            "task_type": task.task_type,
            "acceptance_criteria": task.acceptance_criteria or "",
            "branch_name": task.branch_name or "",
            "sprint_context": context_projection.context_markdown,
            "project_status": context_projection.status_markdown,
            "repo_instructions": self._load_repo_instructions(project.repo_path),
            "spec_path": project.spec_path or "",
            "previous_feedback": carried_output or "",
            "previous_output": latest_run.outcome_detail if latest_run else "",
            # Status describes the tree the agent works in; diffs and log come
            # from refs, which every worktree shares.
            "git_status": self._safe_git_status(self._task_working_dir(project, task)),
            "changed_files": self._safe_changed_files(
                project.repo_path,
                project.default_branch,
                task.branch_name,
            ),
            "recent_commits": self._safe_recent_commits(project.repo_path, task.branch_name),
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
                self._safe_branch_diff_content(
                    project.repo_path,
                    project.default_branch,
                    task.branch_name,
                    max_chars=_int_setting(project, "review_diff_max_chars", default=16000),
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

    def _safe_branch_head(self, project: Project, task: Task) -> str:
        """Return the task branch's head commit, or "" when it cannot be read."""

        if not task.branch_name:
            return ""
        try:
            return head_sha(project.repo_path, f"refs/heads/{task.branch_name}") or ""
        except (GitError, OSError):
            return ""

    def _completion_evidence_stale(
        self,
        evidence: CompletionEvidence,
        task: Task,
        project: Project,
    ) -> bool:
        if not task.branch_name:
            return False
        try:
            current_head = head_sha(project.repo_path, f"refs/heads/{task.branch_name}") or ""
        except Exception:
            return False
        return bool(evidence.head_sha and current_head and evidence.head_sha != current_head)

    def _load_repo_instructions(self, repo_path: str) -> str:
        agents_path = Path(repo_path) / "AGENTS.md"
        if not agents_path.is_file():
            return ""
        return agents_path.read_text(encoding="utf-8")

    def _safe_git_status(self, repo_path: str | Path) -> str:
        try:
            return status_text(repo_path)
        except GitError:
            return ""

    def _safe_changed_files(
        self,
        repo_path: str,
        target_branch: str,
        branch_name: str | None,
    ) -> str:
        try:
            return changed_files(
                repo_path,
                target_branch=target_branch,
                branch_name=branch_name,
            )
        except GitError:
            return ""

    def _safe_recent_commits(self, repo_path: str, branch_name: str | None) -> str:
        try:
            return recent_commits(repo_path, branch_name=branch_name)
        except GitError:
            return ""

    def _prepare_task_branch_for_step(
        self,
        *,
        project: Project,
        task: Task,
        step: str,
        carried_output: str | None,
    ) -> tuple[str | None, tuple[str, dict[str, Any]] | None]:
        """Prepare one task branch before a native role step.

        Merge conflicts are special: the next develop pass should work from an
        existing task branch that has been refreshed against the latest default
        branch whenever that refresh is clean. If the refresh still conflicts,
        carry explicit resolution guidance into the developer prompt and force
        the usual develop -> review cycle after the resolution.
        """

        if step != "develop" or not task.branch_name:
            return carried_output, None

        # Every merge below happens in the task's own worktree; the operator's
        # checkout is never a party to conflict recovery.
        work_dir = self._task_working_dir(project, task)

        if merge_in_progress(work_dir):
            # The previous develop pass was cut off (quota, shutdown) while
            # concluding a merge. Aborting it here would throw away the
            # developer's conflict resolution; leave the tree as it is and say
            # so, because the resumed session knows where it stopped.
            guidance = _append_feedback_note(
                carried_output,
                (
                    f"A merge into branch {task.branch_name!r} is still in progress in the "
                    "working tree (MERGE_HEAD exists) from the previous pass. Finish "
                    "resolving it and commit the merge before continuing the task."
                ),
            )
            return (
                guidance,
                (
                    "engine.branch_sync",
                    {
                        "step": step,
                        "branch": task.branch_name,
                        "target": project.default_branch,
                        "mode": "merge_in_progress",
                        "detail": "Unconcluded merge left by the previous pass; not aborted.",
                    },
                ),
            )

        if not _is_merge_conflict_feedback(carried_output):
            return self._refresh_task_branch(
                project=project,
                task=task,
                step=step,
                carried_output=carried_output,
            )

        sync_result = sync_branch_with_base(
            work_dir,
            task.branch_name,
            project.default_branch,
        )
        if sync_result.success:
            guidance = _append_feedback_note(
                carried_output,
                (
                    f"Foreman refreshed branch {task.branch_name!r} with the latest "
                    f"{project.default_branch!r} before this develop pass. Review the "
                    "merged base-branch changes, make any remaining adjustments, and end "
                    "with TASK_COMPLETE. This conflict-resolution pass will go back "
                    "through code review before merge."
                ),
            )
            return (
                guidance,
                (
                    "engine.branch_sync",
                    {
                        "step": step,
                        "branch": task.branch_name,
                        "target": project.default_branch,
                        "mode": "merge_conflict_recovery",
                        "detail": sync_result.detail,
                    },
                ),
            )

        guidance = _append_feedback_note(
            carried_output,
            (
                f"You are resolving a merge conflict against {project.default_branch!r}. "
                f"Reconcile branch {task.branch_name!r} with the latest "
                f"{project.default_branch!r} so it merges cleanly, then complete another "
                "develop pass. Your conflict-resolution changes will go back through code "
                "review before merge.\n\n"
                f"Latest merge attempt detail:\n{sync_result.detail}"
            ),
        )
        return (
            guidance,
            (
                "engine.branch_sync_conflict",
                {
                    "step": step,
                    "branch": task.branch_name,
                    "target": project.default_branch,
                    "mode": "merge_conflict_recovery",
                    "detail": sync_result.detail,
                },
            ),
        )

    def _refresh_task_branch(
        self,
        *,
        project: Project,
        task: Task,
        step: str,
        carried_output: str | None,
    ) -> tuple[str | None, tuple[str, dict[str, Any]] | None]:
        """Bring a task branch up to date with the default branch before a develop pass.

        A task can wait a long time between visits (a human gate, a quota
        reset, a review round) while the default branch moves. Merging the
        base in now, while the merge is clean, means the developer works on
        current code and the final merge cannot conflict on changes it never
        saw. A refresh that conflicts is handed to the developer as guidance,
        exactly like a merge conflict found at the end.
        """

        branch = task.branch_name or ""
        work_dir = self._task_working_dir(project, task)
        if not branch_exists(project.repo_path, branch):
            return carried_output, None
        behind = commits_behind(project.repo_path, branch, project.default_branch)
        if behind <= 0:
            return carried_output, None
        if not is_worktree_clean(work_dir):
            return carried_output, None

        sync_result = sync_branch_with_base(work_dir, branch, project.default_branch)
        payload = {
            "step": step,
            "branch": branch,
            "target": project.default_branch,
            "mode": "refresh",
            "commits_behind": behind,
            "detail": sync_result.detail,
        }
        if sync_result.success:
            guidance = _append_feedback_note(
                carried_output,
                (
                    f"Foreman refreshed branch {branch!r} with the latest "
                    f"{project.default_branch!r} ({behind} new commit(s)) before this "
                    "develop pass. Review the merged base-branch changes where they touch "
                    "your work; no other action is needed."
                ),
            )
            return guidance, ("engine.branch_sync", payload)

        payload["mode"] = "refresh_conflict"
        guidance = _append_feedback_note(
            carried_output,
            (
                f"Branch {branch!r} is {behind} commit(s) behind {project.default_branch!r} "
                "and merging the base branch into it conflicts. Reconcile the branch with "
                f"the latest {project.default_branch!r} first (resolve the conflict, commit "
                "the merge), then continue the task. The result goes through test and "
                "review as usual.\n\n"
                f"Merge attempt detail:\n{sync_result.detail}"
            ),
        )
        return guidance, ("engine.branch_sync_conflict", payload)

    def _write_runtime_context(
        self,
        run: Run,
        project: Project,
        *,
        context_projection: ProjectContextProjection,
    ) -> None:
        context_projection.write()
        for path in context_projection.written_paths:
            self._emit_event(
                run,
                "engine.context_write",
                {"path": relative_project_path(project, path)},
            )

    def _execute_agent_step_guarded(
        self,
        *,
        run: Run,
        task: Task,
        project: Project,
        **kwargs: Any,
    ) -> AgentExecutionResult:
        """Run one agent step and settle its run row if the engine is interrupted.

        A shutdown signal or a lost lease is not an agent outcome: the run is
        recorded as ``killed`` with an explicit ``agent.killed`` event, the
        task keeps the resume point persisted before the step, and the
        interruption propagates so the engine exits.
        """

        try:
            return self._execute_agent_step(task=task, project=project, **kwargs)
        except LeaseLostError as exc:
            self._abandon_run(
                run,
                task,
                project,
                reason=str(exc),
                gate_type="lease_lost",
                release_lease=False,
            )
            raise
        except EngineCommandInterrupt as exc:
            # An operator asked for this. The run is settled exactly as a
            # shutdown settles it — killed, task resumable at its persisted
            # step — and the resident engine decides afterwards whether the
            # task stays resumable (`pause`) or is parked (`stop_task`).
            self._abandon_run(
                run,
                task,
                project,
                reason=str(exc),
                gate_type="command",
                release_lease=True,
            )
            raise
        except (EngineShutdown, KeyboardInterrupt) as exc:
            self._abandon_run(
                run,
                task,
                project,
                reason=f"Engine stopped before the agent finished: {exc}",
                gate_type="shutdown",
                release_lease=True,
            )
            raise

    def _abandon_run(
        self,
        run: Run,
        task: Task,
        project: Project,
        *,
        reason: str,
        gate_type: str,
        release_lease: bool,
    ) -> None:
        self._emit_event(
            run,
            "agent.killed",
            {"reason": reason, "gate_type": gate_type},
        )
        # The backend announced its session id at start; keep it on the run
        # so the resumed step continues that conversation instead of
        # re-reading the repository from scratch.
        self._complete_run(
            run,
            status="killed",
            outcome=ERROR,
            detail=reason,
            session_id=self._session_id_from_events(run) or run.session_id,
        )
        if release_lease:
            self._release_task_lease(task, project)
        else:
            self._forget_task_lease(task.id)

    def _session_id_from_events(self, run: Run) -> str | None:
        """Return the backend session id announced during ``run``, if any.

        Runners emit ``agent.session`` as soon as the backend reports its
        session (Claude Code's ``init`` line); completion payloads repeat it,
        but a run that is killed or interrupted never reaches completion.
        """

        for event in reversed(self.store.list_events(run_id=run.id)):
            if event.event_type == "agent.session":
                session_id = _optional_string(event.payload.get("session_id"))
                if session_id:
                    return session_id
        return None

    def _execute_agent_step(
        self,
        *,
        role: RoleDefinition,
        project: Project,
        task: Task,
        workflow_step: str,
        prompt: str,
        session_id: str | None,
        carried_output: str | None,
        model: str | None = None,
        event_recorder: Callable[[AgentEventRecord], None] | None = None,
    ) -> AgentExecutionResult:
        try:
            if self.agent_executor is not None:
                return self.agent_executor.execute(
                    role=role,
                    project=project,
                    task=task,
                    workflow_step=workflow_step,
                    prompt=prompt,
                    session_id=session_id,
                    carried_output=carried_output,
                )
            return self._execute_native_runner_step(
                role=role,
                project=project,
                task=task,
                workflow_step=workflow_step,
                prompt=prompt,
                session_id=session_id,
                model=model,
                event_recorder=event_recorder,
            )
        except LeaseLostError:
            raise
        except Exception as exc:  # pragma: no cover - defensive fallback
            return AgentExecutionResult(
                outcome="error",
                detail=str(exc),
                status="failed",
                events=(
                    AgentEventRecord(
                        event_type="agent.error",
                        payload={"error": str(exc)},
                    ),
                ),
            )

    def _execute_native_runner_step(
        self,
        *,
        role: RoleDefinition,
        project: Project,
        task: Task,
        workflow_step: str,
        prompt: str,
        session_id: str | None,
        model: str | None = None,
        event_recorder: Callable[[AgentEventRecord], None] | None = None,
    ) -> AgentExecutionResult:
        runner = self.agent_runners.get(role.agent.backend)
        if runner is None:
            raise OrchestratorError(
                f"No native runner is configured for backend {role.agent.backend!r}."
            )

        if model is None:
            model = resolve_step_model(
                task=task,
                role=role,
                project=project,
                step_id=workflow_step,
                visit_count=task.step_visit_counts.get(workflow_step, 1) or 1,
            )
        model = model or ""
        try:
            resolved_env = resolve_env(role.agent.env)
        except PreflightError as exc:
            return AgentExecutionResult(
                outcome=ERROR,
                detail=str(exc),
                status="failed",
                model=model or None,
                events=(
                    AgentEventRecord(
                        event_type="agent.error",
                        payload={
                            "error": str(exc),
                            "preflight_failed": True,
                        },
                    ),
                ),
                failure_type="preflight",
            )
        config = AgentRunConfig(
            backend=role.agent.backend,
            model=model or None,
            prompt=prompt,
            # The agent edits its task's own worktree, never the operator's
            # checkout.
            working_dir=self._task_working_dir(project, task),
            session_id=session_id,
            permission_mode=role.agent.permission_mode,
            disallowed_tools=role.agent.tools.disallowed,
            extra_flags=role.agent.flags,
            env=resolved_env,
            timeout_seconds=_project_timeout_seconds(
                project,
                role_timeout_minutes=role.completion.timeout_minutes,
            ),
            max_cost_usd=_run_cost_ceiling(project, role.completion.max_cost_usd),
        )
        max_retries = _int_setting(project, "max_infra_retries", default=3)

        events: list[AgentEventRecord] = []
        message_fragments: list[str] = []
        final_message = ""
        saw_final_phase = False
        seen_signals: set[str] = set()
        final_status = "failed"
        outcome = "error"
        detail = ""
        final_session_id = session_id
        cost_usd = 0.0
        aborted_cost_usd = 0.0
        token_count = 0
        token_usage: TokenUsage | None = None
        duration_ms: int | None = None
        failure_type: str | None = None
        retry_after: str | None = None

        retry_kwargs: dict[str, Any] = {"max_retries": max_retries}
        if self.runner_sleep is not None:
            retry_kwargs["sleep"] = self.runner_sleep

        # Heartbeat the task lease while the native runner streams so a long
        # run keeps the lease alive between steps. We track the last heartbeat
        # wall-clock time and only renew once the configured interval has
        # elapsed to avoid hammering SQLite on every event.
        heartbeat_interval = self._native_step_heartbeat_seconds
        last_heartbeat: datetime | None = None

        for event in run_with_retry(
            runner,
            config,
            **retry_kwargs,
        ):
            now = self.utc_now()
            if (
                heartbeat_interval > 0
                and (
                    last_heartbeat is None
                    or (now - last_heartbeat).total_seconds() >= heartbeat_interval
                )
            ):
                self._renew_task_lease(task, project)
                last_heartbeat = now
            if event.event_type == "agent.tick":
                # Silent-child ticks exist only to drive the heartbeat above
                # and the command poll below; they are never persisted. This is
                # the only place a `pause` can reach an agent that has been
                # working quietly for twenty minutes.
                self._poll_commands(task.id)
                continue
            if event.event_type.startswith("signal."):
                # A backend may surface the same signal from more than one
                # stream event, and a replayed attempt re-emits earlier ones.
                signal_key = event.event_type + json.dumps(
                    event.payload, sort_keys=True, default=str
                )
                if signal_key in seen_signals:
                    continue
                seen_signals.add(signal_key)
            event_record = AgentEventRecord(
                event_type=event.event_type,
                payload=dict(event.payload),
                timestamp=event.timestamp,
            )
            events.append(event_record)
            if event_recorder is not None:
                event_recorder(event_record)
            if event.event_type == "agent.message":
                text = _optional_string(event.payload.get("text"))
                if text and (not message_fragments or message_fragments[-1] != text):
                    message_fragments.append(text)
                if text:
                    phase = _optional_string(event.payload.get("phase"))
                    if phase in _FINAL_MESSAGE_PHASES:
                        final_message = text
                        saw_final_phase = True
                    elif not saw_final_phase:
                        final_message = text
                continue

            if event.event_type == "agent.infra_error":
                # The attempt that just failed was charged for; keep its cost
                # on the books and start the next attempt's count from zero.
                aborted_cost_usd += _coerce_float_value(
                    event.payload.get("cost_usd"), default=cost_usd
                )
                cost_usd = 0.0
                token_count = 0
                dropped = _optional_string(event.payload.get("dropped_session_id"))
                if dropped and final_session_id == dropped:
                    final_session_id = None
                continue

            if event.event_type == "agent.cost_update":
                cost_usd = _coerce_float_value(
                    event.payload.get("cumulative_usd"),
                    default=cost_usd,
                )
                token_count = _coerce_int_value(
                    event.payload.get("cumulative_tokens"),
                    default=token_count,
                )
                continue

            if event.event_type == "agent.completed":
                final_session_id = (
                    _optional_string(event.payload.get("session_id")) or final_session_id
                )
                cost_usd = _coerce_float_value(
                    event.payload.get("cost_usd"),
                    default=cost_usd,
                )
                token_count = _coerce_int_value(
                    event.payload.get("token_count"),
                    default=token_count,
                )
                token_usage = TokenUsage.from_mapping(event.payload.get("token_usage")) or token_usage
                duration_ms = _coerce_int_value(
                    event.payload.get("duration_ms"),
                    default=duration_ms,
                )
                outcome, detail = self._extract_completion_output(
                    role,
                    final_message,
                    transcript="\n\n".join(message_fragments),
                )
                final_status = "completed"
                continue

            if event.event_type == "agent.session":
                final_session_id = (
                    _optional_string(event.payload.get("session_id")) or final_session_id
                )
                continue

            if event.event_type == "agent.killed":
                gate_type = _optional_string(event.payload.get("gate_type")) or "gate"
                final_status = "timeout" if gate_type == "time" else "killed"
                outcome = "error"
                detail = (
                    _optional_string(event.payload.get("reason"))
                    or "Agent run was killed by a gate."
                )
                # A backend that stops a run at its budget reports what the
                # run cost; a kill must not erase that from the books.
                final_session_id = (
                    _optional_string(event.payload.get("session_id")) or final_session_id
                )
                cost_usd = _coerce_float_value(event.payload.get("cost_usd"), default=cost_usd)
                token_count = _coerce_int_value(
                    event.payload.get("token_count"), default=token_count
                )
                token_usage = TokenUsage.from_mapping(event.payload.get("token_usage")) or token_usage
                duration_ms = _coerce_int_value(
                    event.payload.get("duration_ms"), default=duration_ms
                )
                continue

            if event.event_type == "agent.error":
                final_session_id = (
                    _optional_string(event.payload.get("session_id")) or final_session_id
                )
                cost_usd = _coerce_float_value(
                    event.payload.get("cost_usd"),
                    default=cost_usd,
                )
                token_count = _coerce_int_value(
                    event.payload.get("token_count"),
                    default=token_count,
                )
                token_usage = TokenUsage.from_mapping(event.payload.get("token_usage")) or token_usage
                duration_ms = _coerce_int_value(
                    event.payload.get("duration_ms"),
                    default=duration_ms,
                )
                final_status = "failed"
                failure_type = _failure_type_for_error(event.payload)
                retry_after = _optional_string(event.payload.get("retry_after"))
                detail = (
                    _optional_string(event.payload.get("error"))
                    or "\n\n".join(message_fragments)
                    or "Agent execution failed."
                )

        if not detail:
            detail = "\n\n".join(message_fragments).strip()
        if not detail:
            detail = "Agent execution finished without output."

        # Each agent.infra_error means run_with_retry aborted an attempt and
        # replayed the step; surface that as the run's retry count so partial
        # duplicate transcripts are diagnosable.
        infra_retry_count = sum(
            1 for record in events if record.event_type == "agent.infra_error"
        )

        return AgentExecutionResult(
            outcome=outcome,
            detail=detail,
            status=final_status,
            session_id=final_session_id,
            cost_usd=cost_usd + aborted_cost_usd,
            token_count=token_count,
            token_usage=token_usage,
            duration_ms=duration_ms,
            model=model or None,
            events=tuple(events),
            events_streamed=event_recorder is not None,
            retry_count=infra_retry_count,
            failure_type=failure_type,
            retry_after=retry_after,
        )

    def _extract_completion_output(
        self,
        role: RoleDefinition,
        text: str,
        *,
        transcript: str | None = None,
    ) -> tuple[str, str]:
        """Apply the role's completion contract to the agent's final message.

        ``text`` is the final assistant message: the marker or verdict must
        appear there, not anywhere in the transcript, so a plan that mentions
        the marker or a reviewer that restates the options never counts.
        ``transcript`` is only a fallback for the returned detail when the
        final message is empty once the marker is stripped.
        """

        cleaned_text = text.strip()
        output_config = role.completion.output
        marker = role.completion.marker.strip()

        if output_config.extract_decision:
            return _extract_decision_output(cleaned_text, allowed=role.completion.outcomes)

        if marker:
            if not _contains_completion_marker(cleaned_text, marker):
                return (ERROR, f"Missing completion marker `{marker}`.")
            cleaned_text = _strip_completion_marker(cleaned_text, marker)
            if not cleaned_text and transcript:
                cleaned_text = _strip_completion_marker(transcript.strip(), marker)

        if output_config.extract_json:
            json_block = _extract_json_block(cleaned_text)
            return (DONE, json_block or cleaned_text or "Completed without JSON output.")

        if output_config.extract_summary or output_config.extract_branch:
            return (DONE, cleaned_text or "Completed.")

        return (DONE, cleaned_text or "Completed.")

    def _output_contract_retry_reason(
        self,
        role: RoleDefinition,
        result: AgentExecutionResult,
    ) -> str | None:
        """Return a retry reason when one malformed agent response merits one corrective retry."""

        if result.status != "completed" or result.outcome != "error":
            return None

        if role.completion.output.extract_decision:
            return "decision_format"

        marker = role.completion.marker.strip()
        if marker and result.detail == f"Missing completion marker `{marker}`.":
            return "missing_completion_marker"

        return None

    def _append_output_contract_retry_instruction(
        self,
        prompt: str,
        role: RoleDefinition,
        reason: str,
    ) -> str:
        """Append a minimal corrective instruction for one malformed-output retry."""

        if reason == "decision_format":
            options = "\n".join(_decision_option_lines(role.completion.outcomes))
            correction = (
                "Your previous response did not follow the required final output format.\n"
                "Do not do more review work.\n"
                "Return exactly one line and nothing else:\n"
                f"{options}"
            )
        elif reason == "missing_completion_marker":
            correction = (
                "Your previous response did not include the required completion marker.\n"
                "Do not do more work.\n"
                f"Return your completion summary again and end with `{role.completion.marker}` "
                "on its own line."
            )
        else:
            return prompt
        return f"{prompt}\n\n### Output Correction\n{correction}"

    def _emit_agent_events(
        self,
        run: Run,
        task: Task,
        project: Project,
        role_id: str,
        events: tuple[AgentEventRecord, ...],
    ) -> None:
        for event_record in events:
            self._emit_event(
                run,
                event_record.event_type,
                event_record.payload,
                role_id=role_id,
                timestamp=event_record.timestamp,
            )
            self._apply_agent_signal(run, task, project, role_id, event_record)

    def _persist_agent_event(
        self,
        run: Run,
        task: Task,
        project: Project,
        role_id: str,
        event_record: AgentEventRecord,
    ) -> None:
        """Persist one agent event immediately while a native step is active."""

        self._emit_event(
            run,
            event_record.event_type,
            event_record.payload,
            role_id=role_id,
            timestamp=event_record.timestamp,
        )
        self._apply_agent_signal(run, task, project, role_id, event_record)

    def _apply_agent_signal(
        self,
        run: Run,
        task: Task,
        project: Project,
        role_id: str,
        event_record: AgentEventRecord,
    ) -> None:
        payload = event_record.payload
        if event_record.event_type.startswith("signal.") and event_record.event_type not in {
            "signal.invalid",
            "signal.unknown",
            "signal.rejected",
        }:
            signal_name = event_record.event_type.removeprefix("signal.")
            role = self.roles.get(role_id)
            if role is not None and signal_name not in role.signals:
                self._emit_event(
                    run,
                    "signal.rejected",
                    {
                        "signal": signal_name,
                        "role_id": role_id,
                        "reason": f"Role {role_id!r} may not emit {signal_name}.",
                    },
                    role_id=role_id,
                )
                return
        if event_record.event_type == "signal.task_started":
            task.title = str(payload.get("title", task.title))
            task.task_type = str(payload.get("task_type", task.task_type))
            task.branch_name = str(payload.get("branch", task.branch_name or "")) or task.branch_name
            task.acceptance_criteria = str(
                payload.get("criteria", task.acceptance_criteria or "")
            ) or task.acceptance_criteria
            self._save_task(task, include_definition=True)
            self._task_started_received.add(task.id)
            return

        if event_record.event_type == "signal.task_created":
            sprint = self.store.get_active_sprint(project.id)
            if sprint is None:
                return
            order_index = self.store.next_task_order_index(sprint.id)
            raw_complexity = _optional_string(payload.get("complexity"))
            complexity = raw_complexity if raw_complexity in TASK_COMPLEXITIES else None
            created_task = Task(
                id=_new_id("task"),
                sprint_id=sprint.id,
                project_id=project.id,
                title=str(payload.get("title", "(agent-created task)")),
                task_type=str(payload.get("task_type", "feature")),
                description=_optional_string(payload.get("description")),
                acceptance_criteria=_optional_string(payload.get("criteria")),
                complexity=complexity,
                order_index=order_index,
                created_by=f"agent:{role_id}",
                created_at=event_record.timestamp,
            )
            self._save_task(created_task)
            self._emit_event(
                run,
                "engine.task_created",
                {
                    "task_id": created_task.id,
                    "title": created_task.title,
                    "task_type": created_task.task_type,
                    "created_by": created_task.created_by,
                },
            )
            return

        if event_record.event_type == "signal.blocker":
            message = _optional_string(payload.get("message"))
            if message:
                task.status = "blocked"
                task.blocked_reason = message
                self._save_task(task)
                self._release_task_lease(task, project)
                self._emit_attention_needed(run, task.id, "task_blocked")

    def _emit_builtin_events(
        self,
        run: Run,
        events: tuple[BuiltinEventRecord, ...],
    ) -> None:
        for event_record in events:
            payload = dict(event_record.payload)
            payload["schema_version"] = event_record.schema_version
            self._emit_event(run, event_record.event_type, payload)

    def _persist_builtin_event(
        self,
        run: Run,
        event_record: BuiltinEventRecord,
    ) -> None:
        """Persist one builtin event immediately while the builtin step is active."""

        payload = dict(event_record.payload)
        payload["schema_version"] = event_record.schema_version
        self._emit_event(run, event_record.event_type, payload)

    def _create_running_run(
        self,
        task: Task,
        *,
        role_id: str,
        workflow_step: str,
        agent_backend: str,
        model: str | None = None,
        branch_name: str | None = None,
        prompt_text: str | None = None,
    ) -> Run:
        now = utc_now_text()
        run = Run(
            id=_new_id("run"),
            task_id=task.id,
            project_id=task.project_id,
            role_id=role_id,
            workflow_step=workflow_step,
            agent_backend=agent_backend,
            status="running",
            model=model,
            branch_name=branch_name,
            prompt_text=prompt_text,
            started_at=now,
            created_at=now,
        )
        self.store.save_run(run)
        return run

    def _create_system_run(
        self,
        task: Task,
        *,
        workflow_step: str,
        outcome: str,
        detail: str,
        role_id: str = "_builtin:orchestrator",
        agent_backend: str = "orchestrator",
        attention_trigger: str | None = None,
    ) -> Run:
        now = utc_now_text()
        run = Run(
            id=_new_id("run"),
            task_id=task.id,
            project_id=task.project_id,
            role_id=role_id,
            workflow_step=workflow_step,
            agent_backend=agent_backend,
            status="completed",
            outcome=outcome,
            outcome_detail=detail,
            started_at=now,
            completed_at=now,
            created_at=now,
        )
        self.store.save_run(run)
        # A blocked system run means the task is transitioning to blocked: raise
        # exactly one attention-needed signal so a manager/human can intervene.
        if outcome == "blocked":
            self._emit_attention_needed(
                run, task.id, attention_trigger or "task_blocked"
            )
        return run

    def _emit_attention_needed(
        self, run: Run, task_id: str | None, trigger: str
    ) -> None:
        """Emit one ``engine.attention_needed`` event for a supervision turn."""
        project = self.store.get_project(run.project_id)
        task = self.store.get_task(task_id) if task_id else None
        self._emit_event(
            run,
            "engine.attention_needed",
            {
                "trigger": trigger,
                "task_id": task_id,
                # What the project asked to be told about, persisted so a
                # later policy change cannot rewrite this moment.
                "notify": self._notification_policy(project, task),
            },
        )

    def _notification_policy(self, project: Project | None, task: Task | None) -> str:
        """Resolve the notification decision for the events worth announcing."""

        return resolve_notification_policy(project, task)

    def _attention_trigger_for_block(self, task: Task) -> str:
        """Pick the supervision trigger for a freshly-blocked task.

        A block driven by a failed completion-evidence proof gate is surfaced as
        ``evidence_failed`` so the digest leads with the proof verdict; any other
        block is the generic ``task_blocked``.
        """
        evidence = task.completion_evidence
        if evidence is not None and getattr(evidence, "proof_status", None) == "failed":
            return "evidence_failed"
        return "task_blocked"

    def _emit_sprint_attention(self, project: Project, sprint: Sprint) -> None:
        """Raise one ``sprint_resolved`` attention turn when a sprint finishes and
        the engine stops (a supervised/directed handoff, or no further sprints).

        Autonomous runs that auto-advance to the next sprint do not call this.
        """
        tasks = self.store.list_tasks(sprint_id=sprint.id)
        anchor = tasks[0] if tasks else self._select_project_system_task(project.id)
        if anchor is None:
            return
        run = self._create_system_run(
            anchor,
            workflow_step="orchestrator",
            outcome="success",
            detail=f"sprint_resolved: {sprint.title}",
        )
        # task_id is None: the digest should lead with the sprint handoff, not a
        # single (already-done) task row.
        self._emit_attention_needed(run, None, "sprint_resolved")

    def _complete_run(
        self,
        run: Run,
        *,
        status: str,
        outcome: str,
        detail: str,
        model: str | None = None,
        session_id: str | None = None,
        cost_usd: float | None = None,
        token_count: int | None = None,
        token_usage: TokenUsage | None = None,
        duration_ms: int | None = None,
        retry_count: int | None = None,
        failure_type: str | None = None,
    ) -> None:
        run.status = status
        run.outcome = outcome
        run.outcome_detail = detail
        if failure_type is not None:
            run.failure_type = failure_type
        run.model = model
        run.session_id = session_id
        if cost_usd is not None:
            run.cost_usd = cost_usd
        if token_count is not None:
            run.token_count = token_count
        if token_usage is not None:
            run.token_usage = token_usage
        if retry_count is not None:
            run.retry_count = retry_count
        run.duration_ms = duration_ms
        run.completed_at = utc_now_text()
        self.store.save_run(run)

    def _emit_event(
        self,
        run: Run,
        event_type: str,
        payload: dict[str, Any],
        *,
        role_id: str | None = None,
        timestamp: str | None = None,
    ) -> Event:
        event = Event(
            id=_new_id("event"),
            run_id=run.id,
            task_id=run.task_id,
            project_id=run.project_id,
            event_type=event_type,
            timestamp=timestamp or utc_now_text(),
            role_id=role_id or run.role_id,
            payload=payload,
        )
        self.store.save_event(event)
        # Mirror every persisted event to the process log so `foreman serve`,
        # which has no terminal, can be understood from its log alone. The
        # level comes from the event family: the narrative at INFO, the agent
        # output firehose at DEBUG, so a resident engine's own lifecycle stays
        # readable. The logger is inert until the CLI configures a handler.
        log_event(
            _LOGGER,
            event.event_type,
            level=event_log_level(event.event_type),
            project_id=event.project_id,
            task_id=event.task_id,
            run_id=event.run_id,
            step=run.workflow_step,
            role_id=event.role_id,
            # Nested rather than flattened: event payloads carry their own
            # ``task_id``/``run_id`` keys whose meaning differs from the row's.
            payload=compact_payload(payload),
        )
        # Notification is a read of the persisted event, not a second source of
        # truth: whatever the audit log says happened is what a destination is
        # told. The dispatcher queues and returns; it never sends here, and it
        # never raises, so no notification setup can fail a run.
        self.notifier.consider(event)
        return event


def _failure_type_for_error(payload: Mapping[str, Any]) -> str:
    """Classify an ``agent.error`` payload for ``Run.failure_type``."""

    if payload.get("quota_exhausted"):
        return "quota"
    if payload.get("preflight_failed"):
        return "preflight"
    if payload.get("retries_exhausted"):
        return "infrastructure"
    return "agent"


def generate_branch_name(task: Task) -> str:
    """Generate a stable branch name for one directed task."""

    prefix = _BRANCH_PREFIXES.get(task.task_type, "feat")
    return f"{prefix}/{task.id}"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


# Complexity → ladder start index when no explicit ladder_start override is set.
_COMPLEXITY_LADDER_START: dict[str, int] = {"small": 0, "medium": 0, "large": 1}


@dataclass(slots=True)
class ModelSelection:
    """The model chosen for one agent step plus the rule that chose it."""

    model: str | None
    source: str  # "override" | "ladder" | "role" | "project_default"


def resolve_step_model_selection(
    *,
    task: Task,
    role: RoleDefinition,
    project: Project,
    step_id: str,
    visit_count: int,
) -> ModelSelection:
    """Resolve the model for one workflow step, recording the deciding rule.

    Precedence (see review.md Phase 3.3):

    1. a per-task override for this step. The ladder still escalates above an
       override that itself appears in the role ladder (resume from its index);
       an override absent from the ladder is pinned for every visit.
    2. the role ``model_ladder`` indexed by ``ladder_start + visit_count - 1``,
       where ``ladder_start`` comes from the task override, else a complexity
       map, else 0.
    3. the role's single ``model``.
    4. the project ``default_model`` setting.
    5. ``None`` (harness default).
    """

    overrides = task.executor_overrides or {}
    ladder = tuple(role.agent.model_ladder)
    step_visit_index = max(visit_count - 1, 0)

    override_model = None
    models_map = overrides.get("models")
    if isinstance(models_map, dict):
        override_model = models_map.get(step_id)

    if override_model:
        if ladder and override_model in ladder:
            base_index = ladder.index(override_model)
            index = min(base_index + step_visit_index, len(ladder) - 1)
            chosen = ladder[index]
            source = "override" if index == base_index else "ladder"
            return ModelSelection(model=chosen, source=source)
        # Pinned deliberately by the manager; keep it for every visit.
        return ModelSelection(model=str(override_model), source="override")

    if ladder:
        ladder_start = overrides.get("ladder_start")
        if not isinstance(ladder_start, int) or isinstance(ladder_start, bool):
            ladder_start = _COMPLEXITY_LADDER_START.get(task.complexity or "", 0)
        index = min(ladder_start + step_visit_index, len(ladder) - 1)
        index = max(index, 0)
        return ModelSelection(model=ladder[index], source="ladder")

    if role.agent.model:
        return ModelSelection(model=role.agent.model, source="role")

    default_model = _string_setting(project, "default_model", default="")
    if default_model:
        return ModelSelection(model=default_model, source="project_default")

    return ModelSelection(model=None, source="project_default")


def resolve_step_model(
    *,
    task: Task,
    role: RoleDefinition,
    project: Project,
    step_id: str,
    visit_count: int,
) -> str | None:
    """Return only the resolved model id for one step (see ``ModelSelection``)."""

    return resolve_step_model_selection(
        task=task,
        role=role,
        project=project,
        step_id=step_id,
        visit_count=visit_count,
    ).model


def resolve_project_settings(project: Project) -> ProjectSettings:
    """Validate a project's raw settings blob, or fail fast with a clear error.

    An unattended engine must not run a misconfigured project on silent
    defaults; invalid settings stop the run before any task is touched.
    """

    try:
        return ProjectSettings.from_raw(project.settings)
    except SettingsError as exc:
        raise OrchestratorError(
            f"Project {project.id!r} has invalid settings: {exc}"
        ) from exc


def _string_setting(project: Project, key: str, *, default: str) -> str:
    value = project.settings.get(key, default)
    return value if isinstance(value, str) else default


def _int_setting(project: Project, key: str, *, default: int) -> int:
    value = project.settings.get(key, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _float_setting(
    project: Project,
    key: str,
    *,
    default: float | None,
) -> float | None:
    value = project.settings.get(key, default)
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float_value(value: Any, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _coerce_int_value(value: Any, *, default: int | None) -> int | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _run_cost_ceiling(project: Project, role_max_cost_usd: float) -> float:
    """Return the cost ceiling for one agent run; 0 means no ceiling.

    The role sets a ceiling and the project's ``runner_max_cost_usd`` may
    lower it. Neither can raise the other.
    """

    ceilings = [
        value
        for value in (
            max(float(role_max_cost_usd or 0.0), 0.0),
            max(_float_setting(project, "runner_max_cost_usd", default=None) or 0.0, 0.0),
        )
        if value > 0
    ]
    return min(ceilings) if ceilings else 0.0


def _project_timeout_seconds(
    project: Project,
    *,
    role_timeout_minutes: int | None = None,
) -> int:
    """Return the effective timeout window for native runs and stale-run recovery."""

    setting = project.settings.get("time_limit_per_run_minutes")
    if isinstance(setting, bool):
        setting = None
    if isinstance(setting, int) and setting > 0:
        return setting * 60
    if isinstance(setting, float) and setting > 0:
        return int(setting * 60)
    if role_timeout_minutes is not None and role_timeout_minutes > 0:
        return role_timeout_minutes * 60
    return 0


def _active_run_recovery_timeout_seconds(project: Project) -> int:
    """Return the stale-run ownership window used for crash recovery."""

    setting = project.settings.get("active_run_recovery_timeout_minutes")
    if isinstance(setting, bool):
        setting = None
    if isinstance(setting, int) and setting > 0:
        return setting * 60
    if isinstance(setting, float) and setting > 0:
        return int(setting * 60)

    project_timeout = _project_timeout_seconds(project)
    default_timeout = 5 * 60
    if project_timeout <= 0:
        return default_timeout
    return min(project_timeout, default_timeout)


def _is_lease_live(
    lease: Lease,
    utc_now: datetime,
    liveness_threshold_seconds: float,
) -> bool:
    """Return True if the lease's heartbeat is recent enough to trust the holder.

    A lease is considered live when its ``heartbeat_at`` is within
    ``liveness_threshold_seconds`` of ``utc_now``. Older heartbeats are
    treated as if the holder is gone so recovery can take over the resource.
    """
    heartbeat = _parse_utc_timestamp(lease.heartbeat_at)
    if heartbeat is None:
        return False
    return (utc_now - heartbeat).total_seconds() <= liveness_threshold_seconds


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


_FINAL_MESSAGE_PHASES = frozenset({"result", "final_answer"})
_DECISION_PREFIX_RE = re.compile(
    r"^(?:(?:final\s+)?(?:decision|verdict|result)\s*[:\-\u2013\u2014]\s*)",
    re.IGNORECASE,
)
_DECISION_LINE_RE = re.compile(r"^(APPROVE|DENY|STEER|ESCALATE)(?![A-Z])\s*(.*)$")
_DECISION_OPTION_TEMPLATES = {
    "approve": "APPROVE",
    "deny": "DENY: <reason>",
    "steer": "STEER: <specific corrective action>",
    "escalate": "ESCALATE: <why the senior reviewer is needed>",
}


def _decision_option_lines(outcomes: tuple[str, ...]) -> list[str]:
    lines = [_DECISION_OPTION_TEMPLATES[o] for o in outcomes if o in _DECISION_OPTION_TEMPLATES]
    return lines or list(_DECISION_OPTION_TEMPLATES.values())[:3]


def _parse_decision_line(raw_line: str) -> tuple[str, str] | None:
    """Return ``(verdict, reason)`` when a line carries a reviewer verdict.

    Accepts the bare word, ``VERDICT: reason``, markdown emphasis, list
    markers, and a ``Decision:`` / ``Verdict:`` prefix. Lines whose reason is
    a ``<placeholder>`` are option restatements, not verdicts, and are ignored.
    """

    line = _normalize_decision_line(raw_line)
    line = _DECISION_PREFIX_RE.sub("", line)
    line = line.strip("*_` ").strip()
    match = _DECISION_LINE_RE.match(line)
    if match is None:
        return None
    verdict = match.group(1).lower()
    reason = match.group(2).strip()
    reason = reason.lstrip(":-\u2013\u2014 ").strip().strip("*_`").strip()
    if reason.startswith("<") and reason.endswith(">"):
        return None
    return (verdict, reason)


def _extract_decision_output(
    text: str,
    *,
    allowed: tuple[str, ...] | None = None,
) -> tuple[str, str]:
    """Extract exactly one reviewer verdict from the final message.

    More than one distinct verdict is an error rather than a guess, and a
    verdict the role does not declare is an error naming the allowed set;
    both trigger the one-shot output-contract retry.
    """

    if not text:
        return (ERROR, "Reviewer returned no decision.")

    found: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        parsed = _parse_decision_line(raw_line)
        if parsed is not None:
            found.append(parsed)
    if not found:
        return (ERROR, text)

    verdicts = {verdict for verdict, _ in found}
    if len(verdicts) > 1:
        return (
            ERROR,
            "Ambiguous decision: found "
            + ", ".join(sorted(v.upper() for v in verdicts))
            + ". Return exactly one verdict.",
        )
    verdict, reason = found[-1]
    if allowed and verdict not in allowed:
        return (
            ERROR,
            f"Decision {verdict.upper()} is not valid for this role; expected one of "
            + ", ".join(o.upper() for o in allowed)
            + ".",
        )
    return (verdict, reason or verdict.upper())


def _normalize_decision_line(line: str) -> str:
    normalized = line.strip()
    normalized = normalized.strip("`")
    normalized = normalized.strip()
    if normalized.startswith(("* ", "- ")):
        normalized = normalized[2:].strip()
    normalized = normalized.strip("*").strip()
    return normalized


def _contains_completion_marker(text: str, marker: str) -> bool:
    return any(_normalize_decision_line(line) == marker for line in text.splitlines())


def _strip_completion_marker(text: str, marker: str) -> str:
    lines = [line for line in text.splitlines() if _normalize_decision_line(line) != marker]
    return "\n".join(lines).strip()


def _is_merge_conflict_feedback(text: str | None) -> bool:
    if not text:
        return False
    normalized = text.lower()
    return "merge conflict against" in normalized or "conflict (" in normalized


def _append_feedback_note(existing: str | None, note: str) -> str:
    existing = (existing or "").strip()
    note = note.strip()
    if not existing:
        return note
    return f"{existing}\n\n{note}"


def _extract_json_block(text: str) -> str | None:
    match = re.search(r"```json\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match is None:
        return None
    return match.group(1).strip() or None
