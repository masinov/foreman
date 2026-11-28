"""The step loop and what it reads and writes between steps.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ...definitions.roles import RoleDefinition
from ...definitions.workflows import WorkflowDefinition
from ...domain.errors import EngineCommandInterrupt
from ...domain.models import CompletionEvidence, Project, Run, Task
from ...domain.outcomes import (
    ASK,
    ERROR,
)
from ...definitions.question import ASKED_EVENT, QUESTION_BLOCKED_REASON, question_of
from ...history.records import RunRecords
from ...repo.context import ProjectContextProjection, relative_project_path
from ...repo.git import (
    head_sha,
    task_commits_on_default_branch,
)
from ...runner.process import EngineShutdown
from ...store import ForemanStore
from ..agent_step import AgentStepRunner
from ..branch_sync import prepare_task_branch_for_step
from ..builtins import BuiltinExecutor
from ..errors import (
    LeaseLostError,
    OrchestratorError,
    QuotaPauseError,
    TaskCancelledError,
)
from ..evidence import EvidenceBuilder
from ..holds import hold_of
from ..leasing import TaskLeases
from ..limits import resolve_project_settings
from ..prompts import PromptBuilder
from ..results import AgentExecutionResult
from ..signals import SignalHandler
from ..step_failures import step_cap_reason
from ..task_worktrees import TaskWorktrees
from ..task_writes import TaskWrites


class WorkflowRunnerBase:
    """The loop: a check, the step, the record, the transition."""

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

    def _wait_for_answer(
        self,
        project: Project,
        task: Task,
        run: Run,
        *,
        step: str,
        carried_output: str | None,
    ) -> Task:
        """Park a task at the step that asked a person a question, holding the queue.

        It waits the way it waits at a human gate (ADR-0039): ``blocked``,
        at ``step``, with its lease let go. The visit that asked did no work
        the step is charged for: the question is not a visit, so the count
        is given back and the step, run again with the answer, takes it up.
        """

        counts = dict(task.step_visit_counts)
        if counts.get(step, 0) > 0:
            counts[step] -= 1
        task.step_visit_counts = counts
        task.status = "blocked"
        task.blocked_reason = QUESTION_BLOCKED_REASON
        task.workflow_current_step = step
        task.workflow_carried_output = carried_output
        self.tasks.save(task)
        question = question_of(run.record) or {}
        self.records.emit_event(run, ASKED_EVENT, {"step": step, "role_id": run.role_id, **question})
        self.records.emit_event(
            run,
            "workflow.paused",
            {
                "step": step,
                "reason": "question",
                "notify": self.records.notification_policy(project, task),
            },
        )
        self.leases.release(task, project)
        return self.store.get_task(task.id) or task

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
                project,
                workflow,
                task,
                step=step,
                carried_output=carried_output,
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
            # A user's hold stops the task here, before its next step
            # (ADR-0043): built-in steps too, so a held task never merges or
            # becomes done, and nothing that waits for it starts.
            if hold_of(self.store, current_task) is not None:
                return self._park_held_task(
                    project, current_task, step=current_step, carried_output=carried_output
                )

            step_def = workflow.get_step(current_step)
            if step_def is None:
                raise OrchestratorError(
                    f"Workflow {workflow.id!r} is missing step {current_step!r}."
                )

            # A merge lands only the commit its gate approved. A branch that
            # moved since has commits nobody tested or reviewed: it goes back
            # to the step a branch brought up to date goes to (test), then
            # review and the gate, for a person to decide on the new head.
            moved = self._moved_since_approval(project, workflow, current_task, step_def)
            if moved is not None:
                gate_step, approved, now_at = moved
                detail = (
                    f"The branch moved after it was approved: approved at {approved[:7]}, "
                    f"it is now at {now_at[:7]}. It goes back to be tested and reviewed."
                )
                payload = {
                    "branch": current_task.branch_name,
                    "target": project.default_branch,
                    "reason": "moved_after_approval",
                    "approved_sha": approved,
                    "head_sha": now_at,
                    "gate_step": gate_step,
                }
                retest = next(
                    (
                        t.to_step
                        for t in workflow.transitions
                        if t.from_step == current_step and t.trigger == "completion:updated"
                    ),
                    None,
                )
                if retest is not None and workflow.get_step(retest) is not None:
                    run = self.records.create_system_run(
                        current_task,
                        workflow_step=current_step,
                        outcome="updated",
                        detail=detail,
                    )
                    self.records.emit_event(
                        run, "engine.merge_blocked", {**payload, "retest_step": retest}
                    )
                    current_task.workflow_current_step = retest
                    current_task.workflow_carried_output = None
                    self.tasks.save(current_task)
                    current_step = retest
                    carried_output = None
                    continue
                current_task.workflow_current_step = gate_step
                current_task.workflow_carried_output = None
                self._block_at_step(
                    current_task,
                    current_step,
                    detail=detail + " Review the new version and decide again.",
                    event_type="engine.merge_blocked",
                    payload=payload,
                )
                break
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

            # A step's own cap is checked first, before the step is entered
            # and counted: a person decides (ADR-0041 section 3). A step that
            # moves up its models gets room for those failures, as the
            # project's max_step_visits does: they are the ladder's, not rounds.
            prior_visits = current_task.step_visit_counts.get(current_step, 0)
            if step_def.max_visits is not None and prior_visits >= step_def.max_visits + self._ladder_visits(
                current_task, current_step, workflow
            ):
                reason = step_cap_reason(current_step, step_def.max_visits)
                # The resume point is this step, whatever cleared it before
                # (a resumed run starts with none): unblocking runs it once more.
                current_task.workflow_current_step = current_step
                self._block_at_step(
                    current_task,
                    current_step,
                    detail=reason,
                    event_type="workflow.step_cap",
                    payload={
                        "step": current_step,
                        "visit_count": prior_visits,
                        "max_visits": step_def.max_visits,
                        "reason": reason,
                    },
                    attention_trigger="loop_limit",
                )
                break

            visit_count = prior_visits + 1
            current_task.step_visit_counts[current_step] = visit_count
            self.tasks.save(current_task)

            settings = resolve_project_settings(project)
            # A step with several models blocks after its last model fails
            # (ADR-0041); its visit limit makes room for those failures, and
            # still bounds a step that keeps dying without failing.
            limit = self._limit_reached(
                current_task,
                current_step,
                visit_count,
                settings,
                extra_visits=self._ladder_visits(current_task, current_step, workflow),
            )
            if limit is not None:
                self._block_at_step(current_task, current_step, **limit)
                break

            exhausted = self._models_exhausted(project, current_task, step_def, current_step)
            if exhausted is not None:
                self._block_at_step(current_task, current_step, **exhausted)
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
                    workflow=workflow,
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
                    workflow=workflow,
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

            if outcome == ASK:
                # The step asked a person: the task waits, and the step runs
                # again with the answer (ADR-0041 section 4). Only after the
                # branch-leak check: a step that asked is checked like any other,
                # or its leaked commits would look like the default branch
                # merely moving once it runs again (sprint 69 review).
                return self._wait_for_answer(
                    project, current_task, run, step=current_step, carried_output=carried_output
                )

            failed_step = self._charge_failure(
                project, workflow, current_task, run, step_def, current_step, outcome
            )
            current_step, carried_output = self._follow_transition(
                project,
                workflow,
                current_task,
                run,
                step=current_step,
                outcome=outcome,
                detail=detail,
                failed_step=failed_step,
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

    def _park_held_task(
        self,
        project: Project,
        task: Task,
        *,
        step: str,
        carried_output: str | None,
    ) -> Task:
        """Leave a held task waiting at ``step``, resumable, and let it go.

        A Block that waited for the step to end is applied now: the task
        becomes ``blocked`` with its reason. A pause, or a block on the
        sprint or the workspace, leaves it ``in_progress`` at ``step``, no
        visit counted, so Resume (or Unblock) carries on from there.
        """

        reason = self.store.apply_requested_block(task.id)
        if reason is not None:
            self.leases.release(task, project)
            blocked = self.store.get_task(task.id) or task
            # Unblock starts the workflow over, as for any blocked task.
            return blocked
        task.status = "in_progress"
        task.workflow_current_step = step
        task.workflow_carried_output = carried_output
        self.tasks.save(task)
        self.leases.release(task, project)
        return self.store.get_task(task.id) or task

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
