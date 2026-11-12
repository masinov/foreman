"""Walking a task through its workflow, one step at a time.

``WorkflowRunner.run_from_step`` runs a task from a step until it stops:
done, blocked, paused at a human gate, cancelled by an operator, or waiting
for a quota to reset. One pass of the loop is one step, and each part of a
step is a method: check the task is still the engine's to work on, check its
worktree and its limits, refresh its branch, run the step (a human gate, a
built-in, or an agent), record what happened, and follow the transition.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import time
from typing import Any

from ..builtins import BuiltinEventRecord, BuiltinExecutor
from ..errors import EngineCommandInterrupt
from ..runner.process import EngineShutdown
from ..context import ProjectContextProjection, build_project_context, relative_project_path
from ..git import GitError, branch_exists, head_sha, task_commits_on_default_branch, worktree_branch
from ..guidance import GUIDANCE_DELIVERED_EVENT, pending_guidance, prompt_with_guidance
from ..models import CompletionEvidence, HumanGateDecision, Project, Run, Task, utc_now_text
from ..outcomes import APPROVE, BLOCKED, ERROR, normalize_agent_outcome, normalize_reviewer_decision
from ..policy import PolicyMatrix, describe_resolution
from ..roles import RoleDefinition
from ..settings import ProjectSettings
from ..store import ForemanStore
from ..workflows import WorkflowDefinition, WorkflowStep
from ..worktrees import WorktreeError
from .agent_step import AgentStepRunner
from .branch_sync import context_mirror_dirs, prepare_task_branch_for_step, task_working_dir
from .errors import LeaseLostError, OrchestratorError, QuotaPauseError, TaskCancelledError
from .evidence import EvidenceBuilder
from .gates import blocked_reason_for_unhandled_outcome, gate_policy_decision
from .leasing import TaskLeases
from .limits import resolve_project_settings
from .model_selection import resolve_step_model_selection
from .output_contract import contract_retry_reason, with_retry_instruction
from .prompts import PromptBuilder
from .records import RunRecords, new_id
from .results import AgentExecutionResult
from .selection import AUTONOMOUS_PLACEHOLDER_TITLE
from .signals import SignalHandler
from .task_worktrees import TaskWorktrees
from .task_writes import TaskWrites


class WorkflowRunner:
    """Runs tasks through workflows for one engine."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        roles: Mapping[str, RoleDefinition],
        records: RunRecords,
        leases: TaskLeases,
        tasks: TaskWrites,
        task_worktrees: TaskWorktrees,
        prompts: PromptBuilder,
        agent_steps: AgentStepRunner,
        signals: SignalHandler,
        evidence: EvidenceBuilder,
        builtin_executor: BuiltinExecutor,
        poll_commands: Callable[[str], None],
        build_evidence: Callable[[Task, Project], CompletionEvidence | None],
    ) -> None:
        self.store = store
        self.roles = roles
        self.records = records
        self.leases = leases
        self.tasks = tasks
        self.task_worktrees = task_worktrees
        self.prompts = prompts
        self.agent_steps = agent_steps
        self.signals = signals
        self.evidence = evidence
        self.builtin_executor = builtin_executor
        self._poll_commands = poll_commands
        #: The engine's entry point for building evidence (see ``PromptBuilder``).
        self.build_completion_evidence = build_evidence

    def pause_for_quota(
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

    def run_from_step(
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
        """Run a task through its workflow from ``step`` until it stops.

        One pass of the loop is one step: check the task is still the
        engine's to work on, check its worktree and its limits, refresh its
        branch, run the step, record what happened, and follow the
        transition. Each of those is a method below.
        """

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

            default_branch = project.default_branch
            original_default_sha = head_sha(project.repo_path, f"refs/heads/{default_branch}")
            refreshed_default_sha: str | None = None
            # The merge and mark-done steps work in the integration tree; every
            # other step works in the task's own.
            uses_task_tree = bool(current_task.branch_name) and step_def.role not in {
                "_builtin:merge",
                "_builtin:mark_done",
            }

            if uses_task_tree:
                problem = self._task_worktree_problem(project, current_task)
                if problem is not None:
                    self._block_at_step(
                        current_task,
                        current_step,
                        detail=problem,
                        event_type="engine.branch_violation",
                        payload={"branch": current_task.branch_name, "detail": problem},
                        clear_resume_point=True,
                    )
                    break

            visit_count = current_task.step_visit_counts.get(current_step, 0) + 1
            current_task.step_visit_counts[current_step] = visit_count
            self.tasks.save(current_task)

            settings = resolve_project_settings(project)
            limit = self._limit_reached(current_task, current_step, visit_count, settings)
            if limit is not None:
                self._block_at_step(current_task, current_step, **limit)
                break

            branch_sync_event: tuple[str, dict[str, Any]] | None = None
            if uses_task_tree:
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
                executed = self._run_human_gate_step(
                    project,
                    current_task,
                    step_def,
                    step=current_step,
                    visit_count=visit_count,
                    carried_output=carried_output,
                )
                if executed is None:
                    # Waiting for a person: the task is paused, not finished.
                    return current_task
            elif step_def.role.startswith("_builtin:"):
                executed = self._run_builtin_step(
                    project,
                    current_task,
                    step_def,
                    step=current_step,
                    visit_count=visit_count,
                    carried_output=carried_output,
                )
            else:
                executed = self._run_agent_step(
                    project,
                    current_task,
                    step_def,
                    step=current_step,
                    visit_count=visit_count,
                    carried_output=carried_output,
                    branch_sync_event=branch_sync_event,
                    session_ids=session_ids,
                )
            run, outcome, detail = executed

            self._record_step_completed(
                run, project, current_task, step_def, current_step, outcome, settings
            )

            # After every step: the task's own work must not be on the default
            # branch before the merge step puts it there. The default branch
            # itself may move (an operator commits, another task merges); that
            # is none of this task's business. ADR-0012.
            leaked_commits: tuple[str, ...] = ()
            if step_def.role != "_builtin:merge" and current_task.branch_name:
                leaked_commits = task_commits_on_default_branch(
                    project.repo_path,
                    task_branch=current_task.branch_name,
                    default_branch=default_branch,
                    default_shas_seen=(original_default_sha, refreshed_default_sha),
                )
            if leaked_commits:
                leak_detail = (
                    f"{len(leaked_commits)} commit(s) from task branch "
                    f"{current_task.branch_name!r} are on {default_branch!r} before the "
                    f"merge step (first: {leaked_commits[0][:12]}). The task's work must "
                    "reach the default branch only through the workflow's merge."
                )
                self._block_at_step(
                    current_task,
                    current_step,
                    detail=leak_detail,
                    event_type="engine.branch_violation",
                    payload={
                        "branch": default_branch,
                        "detail": leak_detail,
                        "commits": list(leaked_commits[:20]),
                    },
                    clear_resume_point=True,
                )
                break

            current_step, carried_output = self._follow_transition(
                project,
                workflow,
                current_task,
                run,
                step=current_step,
                outcome=outcome,
                detail=detail,
            )

            # Renew lease after each step (heartbeat during workflow execution).
            if current_step is not None:
                self.leases.renew(current_task, project)

        # Every path that parks a task leaves it ``blocked``: a gate, a loop
        # or cost limit, a failed guard. A parked task is not being worked on,
        # so nothing may keep holding (and heartbeating) its lease.
        if current_task.status == "blocked":
            self.leases.release(current_task, project)

        return current_task

    def _block_at_step(
        self,
        task: Task,
        step: str,
        *,
        detail: str,
        event_type: str,
        payload: dict[str, Any],
        attention_trigger: str | None = None,
        clear_resume_point: bool = False,
    ) -> None:
        """Park a task as blocked at a step, with a system run saying why.

        ``clear_resume_point`` is for a state the task cannot simply be
        resumed from (its branch or worktree is wrong); a limit leaves the
        resume point so raising the limit lets the task carry on.
        """

        run = self.records.create_system_run(
            task,
            workflow_step=step,
            outcome="blocked",
            detail=detail,
            attention_trigger=attention_trigger,
        )
        self.records.emit_event(run, event_type, payload)
        task.status = "blocked"
        task.blocked_reason = detail
        if clear_resume_point:
            task.workflow_current_step = None
            task.workflow_carried_output = None
        self.tasks.save(task)

    def _branch_commit(self, project: Project, task: Task) -> str | None:
        """The commit the task's branch points at now, or None if it has none."""

        if not task.branch_name:
            return None
        try:
            return head_sha(project.repo_path, f"refs/heads/{task.branch_name}")
        except GitError:
            return None

    def _task_worktree_problem(self, project: Project, task: Task) -> str | None:
        """Say why a task's worktree cannot host a step, or None when it can.

        The operator's checkout is not consulted: what is checked out there
        is none of the engine's business.
        """

        try:
            worktree_path = self.task_worktrees.ensure(project, task)
            if worktree_path is None:
                raise OrchestratorError(f"Task branch {task.branch_name!r} has no worktree.")
            if not branch_exists(project.repo_path, task.branch_name):
                raise OrchestratorError(f"Task branch {task.branch_name!r} does not exist.")
            active_branch = worktree_branch(worktree_path)
            if active_branch != task.branch_name:
                raise OrchestratorError(
                    f"Worktree {worktree_path} should be on task branch "
                    f"{task.branch_name!r} but is on {active_branch!r}."
                )
        except (OrchestratorError, WorktreeError, GitError) as exc:
            return str(exc)
        return None

    def _limit_reached(
        self,
        task: Task,
        step: str,
        visit_count: int,
        settings: ProjectSettings,
    ) -> dict[str, Any] | None:
        """Return how to block the task when a project limit is reached.

        Checked in order: visits to this step, the task's cost, the sprint's
        cost, the task's time. A limit of 0 is off. The result is the keyword
        arguments for ``_block_at_step``.
        """

        max_step_visits = settings.max_step_visits
        if visit_count > max_step_visits:
            return {
                "detail": (
                    f"Step '{step}' visited {visit_count} times "
                    f"(limit: {max_step_visits}). Stuck in a loop."
                ),
                "event_type": "workflow.loop_limit",
                "payload": {
                    "step": step,
                    "visit_count": visit_count,
                    "max_visits": max_step_visits,
                },
                "attention_trigger": "loop_limit",
            }

        task_cost = sum(run.cost_usd for run in self.store.list_runs(task_id=task.id))
        cost_limit = settings.cost_limit_per_task_usd
        # 0 is the documented "off" value, and what the settings screen saves.
        if cost_limit > 0 and task_cost >= cost_limit:
            return {
                "detail": f"Task cost ${task_cost:.2f} exceeds limit ${cost_limit:.2f}",
                "event_type": "gate.cost_exceeded",
                "payload": {"limit_usd": cost_limit, "actual_usd": task_cost, "scope": "task"},
            }

        sprint_cost_limit = settings.cost_limit_per_sprint_usd
        sprint_cost = float(self.store.run_totals(sprint_id=task.sprint_id)["total_cost_usd"])
        if sprint_cost_limit > 0 and sprint_cost >= sprint_cost_limit:
            return {
                "detail": (
                    f"Sprint cost ${sprint_cost:.2f} exceeds limit ${sprint_cost_limit:.2f}"
                ),
                "event_type": "gate.cost_exceeded",
                "payload": {
                    "limit_usd": sprint_cost_limit,
                    "actual_usd": sprint_cost,
                    "scope": "sprint",
                },
            }

        task_duration_ms = sum(
            run.duration_ms or 0 for run in self.store.list_runs(task_id=task.id)
        )
        time_limit_ms = settings.time_limit_per_task_ms
        if time_limit_ms > 0 and task_duration_ms >= time_limit_ms:
            return {
                "detail": (
                    f"Task time {task_duration_ms/1000:.1f}s exceeds limit "
                    f"{time_limit_ms/1000:.1f}s"
                ),
                "event_type": "gate.time_exceeded",
                "payload": {
                    "task_id": task.id,
                    "total_duration_ms": task_duration_ms,
                    "time_limit_ms": time_limit_ms,
                },
            }
        return None

    def _run_human_gate_step(
        self,
        project: Project,
        task: Task,
        step_def: WorkflowStep,
        *,
        step: str,
        visit_count: int,
        carried_output: str | None,
    ) -> tuple[Run, str, str] | None:
        """Run a human-gate step. Returns None when the task now waits for a person.

        Policy may decide the gate on its own (``auto``), in which case the
        step has an outcome like any other.
        """

        run = self.records.create_running_run(
            task,
            role_id=step_def.role,
            workflow_step=step,
            agent_backend="builtin",
        )
        self.records.emit_event(
            run,
            "workflow.step_started",
            {"step": step, "visit_count": visit_count},
        )
        self._emit_policy_resolved(run, project, task)
        gate_policy = gate_policy_decision(project, task, step_def)
        if gate_policy == "auto":
            outcome, detail = self._auto_approve_gate(
                run, project, task, step_def
            )
        else:
            result = self.builtin_executor.execute(
                step_def.role,
                project=project,
                task=task,
                step_id=step,
                carried_output=carried_output,
                store=self.store,
                event_recorder=lambda event_record: self.persist_builtin_event(run, event_record),
                working_dir=task_working_dir(project, task),
            )
            self.tasks.save(task)
            self.records.complete_run(
                run,
                status="completed",
                outcome=result.outcome,
                detail=result.detail,
            )
            self.emit_builtin_events(run, result.events)
            self.records.emit_event(
                run,
                "workflow.paused",
                {
                    "step": step,
                    "reason": "human_gate",
                    "policy": step_def.policy,
                    # What the project asked to be told about; the
                    # delivery worker acts on this persisted decision.
                    "notify": self.records.notification_policy(project, task),
                },
            )
            # A task waiting for a person is not being worked on. Left
            # held, the lease made the engine wait out its remaining
            # lifetime before it could act on the decision.
            self.leases.release(task, project)
            return None
        return run, outcome, detail

    def _run_builtin_step(
        self,
        project: Project,
        task: Task,
        step_def: WorkflowStep,
        *,
        step: str,
        visit_count: int,
        carried_output: str | None,
    ) -> tuple[Run, str, str]:
        """Run a built-in step (tests, merge, mark done) and record its run."""

        run = self.records.create_running_run(
            task,
            role_id=step_def.role,
            workflow_step=step,
            agent_backend="builtin",
        )
        self.records.emit_event(
            run,
            "workflow.step_started",
            {"step": step, "visit_count": visit_count},
        )
        self._emit_policy_resolved(run, project, task)
        builtin_started = time.monotonic()
        result = self.builtin_executor.execute(
            step_def.role,
            project=project,
            task=task,
            step_id=step,
            carried_output=carried_output,
            store=self.store,
            evidence_builder=self.build_completion_evidence,
            working_dir=task_working_dir(project, task),
        )
        self.tasks.save(task)
        self.records.complete_run(
            run,
            status="completed",
            outcome=result.outcome,
            detail=result.detail,
            # A test run or a merge takes real time; recording 0 made
            # every built-in step look instantaneous.
            duration_ms=int((time.monotonic() - builtin_started) * 1000),
        )
        self.emit_builtin_events(run, result.events)
        # A builtin that blocks (e.g. the merge/mark_done completion
        # guard rejecting weak evidence) sets the task to blocked itself
        # and never routes through ``_create_system_run``; raise the one
        # attention-needed turn here so supervision still fires.
        if result.outcome == BLOCKED:
            self.records.emit_attention_needed(
                run,
                task.id,
                self.records.attention_trigger_for_block(task),
            )
        outcome = normalize_agent_outcome(result.outcome)
        detail = result.detail
        return run, outcome, detail

    def _run_agent_step(
        self,
        project: Project,
        task: Task,
        step_def: WorkflowStep,
        *,
        step: str,
        visit_count: int,
        carried_output: str | None,
        branch_sync_event: tuple[str, dict[str, Any]] | None,
        session_ids: dict[tuple[str, str], str],
    ) -> tuple[Run, str, str]:
        """Run an agent step: build the prompt, run the role, record the run.

        A response that breaks the role's output contract gets one corrective
        retry. A quota stop pauses the task and raises ``QuotaPauseError``.
        """

        role = self.roles.get(step_def.role)
        if role is None:
            raise OrchestratorError(f"Unknown role {step_def.role!r}.")
        task.assigned_role = role.id
        self.tasks.save(task)

        context_projection = build_project_context(
            self.store,
            project,
            current_task=task,
            carried_output=carried_output,
            mirror_dirs=context_mirror_dirs(project, task),
        )
        prompt = self.prompts.build(
            role,
            project,
            task,
            carried_output,
            context_projection=context_projection,
        )
        # Notes a person wrote for this task since the last agent step
        # go into this prompt, and are marked delivered once the run
        # that carries them exists.
        guidance = pending_guidance(self.store.list_events(task_id=task.id))
        prompt = prompt_with_guidance(prompt, guidance)
        model_selection = resolve_step_model_selection(
            task=task,
            role=role,
            project=project,
            step_id=step,
            visit_count=visit_count,
        )
        model = model_selection.model or ""
        run = self.records.create_running_run(
            task,
            role_id=role.id,
            workflow_step=step,
            agent_backend=role.agent.backend,
            model=model_selection.model,
            branch_name=task.branch_name,
            prompt_text=prompt,
        )
        self.records.emit_event(
            run,
            "workflow.model_selected",
            {
                "step": step,
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
        self.write_runtime_context(
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
                    "step": step,
                },
            )
        self.records.emit_event(
            run,
            "workflow.step_started",
            {"step": step, "visit_count": visit_count},
        )
        self._emit_policy_resolved(run, project, task)
        if branch_sync_event is not None:
            event_type, payload = branch_sync_event
            self.records.emit_event(run, event_type, payload)
        session_key = (role.id, role.agent.backend)
        session_id: str | None = None
        if role.agent.session_persistence:
            session_id = session_ids.get(session_key)
            if session_id is None:
                session_id = self.store.get_latest_session_id(
                    task_id=task.id,
                    role_id=role.id,
                    agent_backend=role.agent.backend,
                )
                if session_id:
                    session_ids[session_key] = session_id
        result = self.agent_steps.execute_guarded(
            run=run,
            role=role,
            project=project,
            task=task,
            workflow_step=step,
            prompt=prompt,
            session_id=session_id,
            carried_output=carried_output,
            model=model_selection.model,
            event_recorder=lambda event_record: self.signals.persist_agent_event(
                run,
                task,
                project,
                role.id,
                event_record,
            ),
        )
        if not result.events_streamed:
            self.signals.emit_agent_events(run, task, project, role.id, result.events)
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
            commit_sha=self._branch_commit(project, task),
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
                    "step": step,
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
                task,
                role_id=role.id,
                workflow_step=step,
                agent_backend=role.agent.backend,
                model=model or None,
                branch_name=task.branch_name,
                prompt_text=retry_prompt,
            )
            self.write_runtime_context(
                retry_run,
                project,
                context_projection=context_projection,
            )
            self.records.emit_event(
                retry_run,
                "workflow.step_started",
                {
                    "step": step,
                    "visit_count": visit_count,
                    "retry_attempt": 1,
                },
            )
            retry_result = self.agent_steps.execute_guarded(
                run=retry_run,
                role=role,
                project=project,
                task=task,
                workflow_step=step,
                prompt=retry_prompt,
                session_id=retry_session_id,
                carried_output=carried_output,
                model=model_selection.model,
                event_recorder=lambda event_record: self.signals.persist_agent_event(
                    retry_run,
                    task,
                    project,
                    role.id,
                    event_record,
                ),
            )
            if not retry_result.events_streamed:
                self.signals.emit_agent_events(
                    retry_run,
                    task,
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
                commit_sha=self._branch_commit(project, task),
            )
            run = retry_run
            result = retry_result
        if result.failure_type == "quota":
            self.pause_for_quota(
                project,
                task,
                run,
                step=step,
                carried_output=carried_output,
                result=result,
            )
            raise QuotaPauseError(
                task.id,
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
                    "head_sha": self.evidence.branch_head(project, task),
                },
            )
        else:
            outcome = normalize_agent_outcome(result.outcome)
        detail = result.detail
        return run, outcome, detail

    def _record_step_completed(
        self,
        run: Run,
        project: Project,
        task: Task,
        step_def: WorkflowStep,
        step: str,
        outcome: str,
        settings: ProjectSettings,
    ) -> None:
        """Record that a step finished, and what follows from it for the task."""

        # ── Autonomous mode: an agent that never named its task ──
        # The agent is asked to report what it chose to work on with
        # signal.task_started. If it has not after a step that may send
        # that signal, the task goes on as it is (spec §6.2: degraded but
        # functional). The gap is recorded once, and what is recorded for
        # the task is read from the store, so a restart changes nothing.
        if (
            settings.task_selection_mode == "autonomous"
            and task.created_by == "orchestrator"
            and task.title == AUTONOMOUS_PLACEHOLDER_TITLE
            and step_def.role in self.roles
            and "task_started" in self.roles[step_def.role].signals
            and not self.signals.autonomous_gap_recorded(task)
        ):
            self.records.emit_event(
                run,
                "workflow.autonomous_contract_missing",
                {
                    "task_id": task.id,
                    "step": step,
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
            {"step": step, "outcome": outcome},
        )

        # Evidence built for the reviewer's prompt predates the review. Now
        # that a decision exists, record it, so the task shows what was
        # decided rather than "no review yet" until the merge step.
        if (
            task.completion_evidence is not None
            and not step_def.role.startswith("_builtin:")
            and step_def.role in self.roles
            and self.roles[step_def.role].completion.output.extract_decision
        ):
            task.completion_evidence = self.build_completion_evidence(
                task, project
            )
            self.tasks.save(task)

    def _follow_transition(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
        run: Run,
        *,
        step: str,
        outcome: str,
        detail: str,
    ) -> tuple[str | None, str | None]:
        """Move the task along its workflow. Returns the next step and what it carries.

        The next step is None when the workflow ends here: the task is done,
        or no transition handles the outcome and the task is blocked.
        """

        transition = workflow.find_transition(step, outcome)
        if transition is None:
            if task.status != "done":
                self.records.emit_event(
                    run,
                    "workflow.no_transition",
                    {"step": step, "outcome": outcome},
                )
                task.status = "blocked"
                task.blocked_reason = blocked_reason_for_unhandled_outcome(
                    workflow=workflow,
                    step=step,
                    outcome=outcome,
                    detail=detail,
                )
            task.workflow_current_step = None
            task.workflow_carried_output = None
            self.tasks.save(task)
            self.leases.release(task, project)
            return None, None

        self.records.emit_event(
            run,
            "workflow.transition",
            {
                "from_step": step,
                "to_step": transition.to_step,
                "trigger": transition.trigger,
            },
        )
        carried_output = detail if transition.carry_output else None
        if transition.trigger == "completion:conflict":
            task.step_visit_counts = {}
            self.records.emit_event(
                run,
                "workflow.step_visit_reset",
                {
                    "reason": "merge_conflict_recovery",
                    "from_step": step,
                    "to_step": transition.to_step,
                },
            )
        # The next step is recorded in the same write that leaves this one. A
        # crash before that step starts then resumes there; with the step
        # cleared first, recovery restarted the whole task and an approval
        # recorded a moment earlier was lost.
        task.workflow_current_step = transition.to_step
        task.workflow_carried_output = carried_output if transition.to_step is not None else None
        self.tasks.save(task)
        return transition.to_step, carried_output

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

    def write_runtime_context(
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

    def emit_builtin_events(
        self,
        run: Run,
        events: tuple[BuiltinEventRecord, ...],
    ) -> None:
        for event_record in events:
            payload = dict(event_record.payload)
            payload["schema_version"] = event_record.schema_version
            self.records.emit_event(run, event_record.event_type, payload)

    def persist_builtin_event(
        self,
        run: Run,
        event_record: BuiltinEventRecord,
    ) -> None:
        """Persist one builtin event immediately while the builtin step is active."""

        payload = dict(event_record.payload)
        payload["schema_version"] = event_record.schema_version
        self.records.emit_event(run, event_record.event_type, payload)
