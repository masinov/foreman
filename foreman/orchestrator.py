"""Task orchestration for Foreman workflow execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess
from typing import Any, Protocol
from uuid import uuid4

from .builtins import BuiltinEventRecord, BuiltinExecutor
from .context import ProjectContextProjection, build_project_context, relative_project_path
from .errors import ForemanError
from .git import (
    GitError,
    assert_default_branch_unchanged,
    assert_not_on_default_branch,
    branch_exists,
    changed_files,
    checkout_branch,
    current_branch,
    head_sha,
    is_worktree_clean,
    recent_commits,
    status_text,
    sync_branch_with_base,
    worktree_branch,
)
from .leases import generate_lease_token
from .models import CompletionEvidence, Event, Project, Run, Sprint, Task, utc_now_text
from .outcomes import APPROVE, BLOCKED, DENY, DONE, ERROR, normalize_agent_outcome, normalize_reviewer_decision, STEER
from .runner import AgentRunConfig, ClaudeCodeRunner, CodexRunner, run_with_retry
from .runner.base import AgentRunner as NativeAgentRunner
from .roles import RoleDefinition, default_roles_dir, load_roles
from .store import ForemanStore
from .workflows import WorkflowDefinition, default_workflows_dir, load_workflows

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
    duration_ms: int | None = None
    model: str | None = None
    events: tuple[AgentEventRecord, ...] = ()
    events_streamed: bool = False


@dataclass(slots=True)
class ProjectRunResult:
    """Summary of one orchestrator invocation."""

    project_id: str
    executed_task_ids: tuple[str, ...]
    blocked_task_ids: tuple[str, ...]
    stop_reason: str


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


@dataclass(slots=True)
class SupervisorMergeResult:
    """Summary of one supervisor merge finalization."""

    project_id: str
    task_id: str
    sprint_id: str
    task_status: str
    sprint_status: str
    stop_reason: str | None = None
    completion_evidence: "CompletionEvidence | None" = None


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
    ) -> None:
        loaded_roles = dict(roles) if roles is not None else load_roles(default_roles_dir())
        loaded_workflows = (
            dict(workflows)
            if workflows is not None
            else load_workflows(
                default_workflows_dir(),
                available_role_ids=set(loaded_roles),
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
        self.runner_sleep = runner_sleep
        self.utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self.holder_id = holder_id or str(uuid4())
        self._task_lease_tokens: dict[str, str] = {}
        self._task_started_received: set[str] = set()

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

    def _release_task_lease(self, task: Task, project: Project) -> None:
        """Release the lease on a task if held by this orchestrator."""
        token = self._task_lease_tokens.pop(task.id, None)
        if token is not None:
            self.store.release_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
                holder_id=self.holder_id,
                lease_token=token,
            )

    def _renew_task_lease(self, task: Task, project: Project) -> None:
        """Renew the lease on a task if held by this orchestrator."""
        token = self._task_lease_tokens.get(task.id)
        if token is not None:
            self.store.renew_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
                holder_id=self.holder_id,
                lease_token=token,
            )

    def run_project(
        self,
        project_id: str,
        *,
        task_id: str | None = None,
    ) -> ProjectRunResult:
        """Run one project's active workflow until no runnable task remains."""

        project = self.store.get_project(project_id)
        if project is None:
            raise OrchestratorError(f"Unknown project {project_id!r}.")
        workflow = self._load_workflow_for_project(project)
        self.prune_old_history(project)
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
            completed = self.run_task(project, workflow, task)
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
                completed = self.run_task(project, workflow, task)
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

        Gathers acceptance-criteria coverage, branch diff stats, agent outputs,
        and built-in test results to produce a score and verdict that
        downstream review can use without trusting developer markers or
        reviewer approval alone.
        """
        runs = self.store.list_runs(task_id=task.id)

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
        for event in sorted(test_events, key=lambda e: e.timestamp):
            payload = event.payload
            if event.event_type == "engine.test_run":
                builtin_test_result = payload.get("command", "")
                # Derive passed from exit_code rather than a separate field
                builtin_test_passed = payload.get("exit_code") == 0
            elif event.event_type == "engine.test_output":
                if payload.get("exit_code") == 0:
                    builtin_test_passed = True
                builtin_test_detail = payload.get("output", "")

        # Criteria coverage
        criteria_count = 0
        criteria_addressed = 0
        criteria_partially_addressed = 0
        criteria_text = task.acceptance_criteria or ""
        criteria_list = [c.strip() for c in criteria_text.split("\n") if c.strip()]
        criteria_count = len(criteria_list)

        if criteria_list:
            all_output_text = "\n".join(agent_outputs).lower()
            for criterion in criteria_list:
                addressed, partial = self._criterion_addressed(criterion, all_output_text, changed_files)
                if addressed:
                    criteria_addressed += 1
                elif partial:
                    criteria_partially_addressed += 1

        score, breakdown = self._score_evidence(
            criteria_count=criteria_count,
            criteria_addressed=criteria_addressed,
            criteria_partially_addressed=criteria_partially_addressed,
            changed_files=changed_files,
            diff_context_lines=diff_context_lines,
            builtin_test_passed=builtin_test_passed,
            builtin_test_result=builtin_test_result,
            agent_outputs=agent_outputs,
        )
        verdict, reasons = self._verdict_from_score(score, criteria_count, criteria_addressed)

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
            score=score,
            score_breakdown=breakdown,
            verdict=verdict,
            verdict_reasons=tuple(reasons),
        )

    def _safe_branch_diff(
        self,
        repo_path: str,
        target_branch: str,
        branch_name: str,
    ) -> str:
        """Return diff text for one branch, or empty string on failure."""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", f"{target_branch}...{branch_name}"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:  # pragma: no cover
            pass
        try:
            result2 = subprocess.run(
                ["git", "diff", target_branch, branch_name, "--stat"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
            )
            if result2.returncode == 0:
                return result2.stdout
        except Exception:  # pragma: no cover
            pass
        return ""

    def _parse_diff_stats(
        self,
        diff_output: str,
    ) -> tuple[tuple[str, ...], int, str]:
        """Parse git diff --stat output into structured fields.

        Returns (changed_files, total_context_lines, summary_line).
        """
        lines = [l.strip() for l in diff_output.strip().splitlines() if l.strip()]
        changed_files: list[str] = []
        total_additions = 0
        total_deletions = 0
        context_lines = 0

        for line in lines:
            if " | " in line and "Binary" not in line:
                parts = line.split()
                if parts:
                    changed_files.append(parts[0])
                if "+" in line:
                    match = re.search(r"(\d+)\s*\+", line)
                    if match:
                        total_additions += int(match.group(1))
                if "-" in line:
                    match = re.search(r"(\d+)\s*-", line)
                    if match:
                        total_deletions += int(match.group(1))
            elif re.match(r"\d+ file", line):
                pass  # summary line captured below
            elif re.match(r"\d+ insertion", line) or re.match(r"\d+ deletion", line):
                pass  # cumulative stat line
            context_lines += 1

        summary = f"{len(changed_files)} file(s), +{total_additions}, -{total_deletions}"
        return (tuple(changed_files), context_lines, summary)

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

    def _criterion_addressed(
        self,
        criterion: str,
        output_text: str,
        changed_files: tuple[str, ...],
    ) -> tuple[bool, bool]:
        """Return (addressed, partially_addressed) for one acceptance criterion.

        A criterion is addressed when the output text or changed files
        contain substantive references to its key terms.  Partial coverage
        is when only a subset of the relevant terms appear.
        """
        key_terms = [
            t.strip().rstrip(".,;:!?()[]{}'\"").strip()
            for t in re.findall(r"\b\w{4,}\b", criterion.lower())
        ]
        if not key_terms:
            return (False, False)

        matching_terms = sum(
            1 for term in key_terms if term in output_text or any(term in f.lower() for f in changed_files)
        )
        coverage_ratio = matching_terms / len(key_terms)

        if coverage_ratio >= 0.7:
            return (True, False)
        if coverage_ratio >= 0.3:
            return (False, True)
        return (False, False)

    def _score_evidence(
        self,
        *,
        criteria_count: int,
        criteria_addressed: int,
        criteria_partially_addressed: int,
        changed_files: tuple[str, ...],
        diff_context_lines: int,
        builtin_test_passed: bool,
        builtin_test_result: str,
        agent_outputs: tuple[str, ...],
    ) -> tuple[float, str]:
        """Compute a 0–100 evidence score with a human-readable breakdown."""
        score = 0.0
        parts: list[str] = []

        # Criteria coverage: up to 40 points
        if criteria_count > 0:
            criteria_score = (criteria_addressed * 40 / criteria_count) + (
                criteria_partially_addressed * 15 / criteria_count
            )
        else:
            criteria_score = 0.0
        score += min(criteria_score, 40)
        parts.append(f"criteria={min(criteria_score, 40):.1f}/40")

        # Code change breadth: up to 20 points
        file_score = min(len(changed_files) * 5, 20)
        score += file_score
        parts.append(f"files={file_score:.1f}/20 ({len(changed_files)} changed)")

        # Diff context: up to 10 points
        diff_score = min(diff_context_lines * 0.5, 10)
        score += diff_score
        parts.append(f"diff={diff_score:.1f}/10 ({diff_context_lines} context lines)")

        # Built-in test: up to 30 points
        if builtin_test_result:
            test_score = 30 if builtin_test_passed else 0
        else:
            test_score = 0
        score += test_score
        parts.append(f"test={test_score:.1f}/30 (passed={builtin_test_passed})")

        breakdown = "; ".join(parts)
        return (round(score, 2), breakdown)

    def _verdict_from_score(
        self,
        score: float,
        criteria_count: int,
        criteria_addressed: int,
    ) -> tuple[str, list[str]]:
        """Translate a numeric score into a completion verdict with reasons."""
        reasons: list[str] = []

        if score >= 75 and criteria_addressed >= criteria_count:
            verdict = "strong"
            reasons.append("All acceptance criteria addressed with good evidence")
        elif score >= 60 and criteria_addressed >= max(1, criteria_count // 2):
            verdict = "adequate"
            reasons.append("Sufficient evidence of task completion")
        elif score >= 40:
            verdict = "weak"
            reasons.append("Incomplete coverage of acceptance criteria")
        else:
            verdict = "insufficient"
            reasons.append("Insufficient evidence for task completion")

        if criteria_count == 0:
            reasons.append("No acceptance criteria defined")
        elif criteria_addressed == 0 and criteria_count > 0:
            reasons.append("No acceptance criteria were addressed")

        if not reasons:
            reasons.append("Unable to determine verdict from available evidence")

        return verdict, reasons

    def finalize_supervisor_merge(
        self,
        *,
        repo_path: str,
        branch_name: str,
        task_id: str | None = None,
    ) -> SupervisorMergeResult | None:
        """Persist task and sprint state after a reviewed supervisor merge."""

        project = self.store.find_project_by_repo_path(repo_path)
        if project is None:
            return None

        task = self.store.get_task(task_id) if task_id else None
        if task is not None and task.project_id != project.id:
            return None
        if task is None:
            task = self.store.find_task_by_branch(project_id=project.id, branch_name=branch_name)
        if task is None:
            return None

        completion_evidence: CompletionEvidence | None = None
        if task.status != "done":
            task.status = "done"
            task.blocked_reason = None
            task.workflow_current_step = None
            task.workflow_carried_output = None
            task.completed_at = task.completed_at or utc_now_text()
            completion_evidence = self.build_completion_evidence(task, project)
            task.completion_evidence = completion_evidence
            self.store.save_task(task)
            self._release_task_lease(task, project)

            run = self._create_system_run(
                task,
                workflow_step="supervisor_finalize",
                outcome="success",
                detail=f"Supervisor merged {branch_name} into {project.default_branch}.",
            )
            self._emit_event(
                run,
                "engine.supervisor_merge",
                {
                    "branch": branch_name,
                    "target": project.default_branch,
                    "task_id": task.id,
                    "evidence_score": completion_evidence.score if completion_evidence else None,
                    "evidence_verdict": completion_evidence.verdict if completion_evidence else None,
                },
            )
            self._emit_event(
                run,
                "engine.completion_evidence",
                {
                    "task_id": task.id,
                    "criteria_count": completion_evidence.criteria_count if completion_evidence else 0,
                    "criteria_addressed": completion_evidence.criteria_addressed if completion_evidence else 0,
                    "criteria_partially_addressed": (
                        completion_evidence.criteria_partially_addressed if completion_evidence else 0
                    ),
                    "changed_files": list(completion_evidence.changed_files) if completion_evidence else [],
                    "builtin_test_passed": (
                        completion_evidence.builtin_test_passed if completion_evidence else False
                    ),
                    "score": completion_evidence.score if completion_evidence else 0.0,
                    "verdict": completion_evidence.verdict if completion_evidence else "unknown",
                },
            )

        sprint = self.store.get_sprint(task.sprint_id)
        stop_reason: str | None = None
        if sprint is not None and sprint.status == "active" and self._sprint_fully_resolved(sprint):
            stop_reason = self._advance_sprint(project, sprint)
            sprint = self.store.get_sprint(task.sprint_id) or sprint

        return SupervisorMergeResult(
            project_id=project.id,
            task_id=task.id,
            sprint_id=task.sprint_id,
            task_status=task.status,
            sprint_status=sprint.status if sprint is not None else "unknown",
            stop_reason=stop_reason,
            completion_evidence=completion_evidence,
        )

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
        self.store.save_task(placeholder)
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
        restore_branch = self._safe_current_branch(project.repo_path)

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
            checkout_branch(
                project.repo_path,
                current_task.branch_name,
                create=True,
                base_branch=project.default_branch,
            )

        current_task.status = "in_progress"
        current_task.blocked_reason = None
        current_task.workflow_current_step = None
        current_task.workflow_carried_output = None
        if not is_resuming:
            current_task.step_visit_counts = {}
        current_task.started_at = current_task.started_at or utc_now_text()
        self.store.save_task(current_task)

        try:
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
                    ),
                )
            return refreshed
        finally:
            self._restore_branch_if_safe(project.repo_path, restore_branch)

    def resume_human_gate(
        self,
        task_id: str,
        *,
        outcome: str,
        note: str | None = None,
    ) -> HumanGateResumeResult:
        """Apply one human-gate decision and continue execution when possible."""

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

        current_task.status = "in_progress"
        current_task.blocked_reason = None
        current_task.workflow_current_step = None
        current_task.workflow_carried_output = None
        self.store.save_task(current_task)

        if deferred:
            current_task.workflow_current_step = transition.to_step
            current_task.workflow_carried_output = carried_output
            self.store.save_task(current_task)
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

        restore_branch = self._safe_current_branch(project.repo_path)
        if str(project.settings.get("task_selection_mode", "directed")) == "directed":
            current_task.branch_name = current_task.branch_name or generate_branch_name(
                current_task
            )
            checkout_branch(
                project.repo_path,
                current_task.branch_name,
                create=True,
                base_branch=project.default_branch,
            )

        try:
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
        finally:
            self._restore_branch_if_safe(project.repo_path, restore_branch)

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

        current_task = self.store.get_task(task.id) or task
        current_step = step
        session_ids: dict[tuple[str, str], str] = {}

        while current_step is not None:
            step_def = workflow.get_step(current_step)
            if step_def is None:
                raise OrchestratorError(
                    f"Workflow {workflow.id!r} is missing step {current_step!r}."
                )

            # ── Before every step: enforce branch invariants ─────────────────
            default_branch = project.default_branch
            original_default_sha = head_sha(project.repo_path, f"refs/heads/{default_branch}")

            # Verify task branch exists (for native role steps) or is being created.
            if step_def.role not in {"_builtin:merge", "_builtin:mark_done"}:
                if current_task.branch_name:
                    if not branch_exists(project.repo_path, current_task.branch_name):
                        raise OrchestratorError(
                            f"Task branch {current_task.branch_name!r} does not exist."
                        )
                    # In directed mode, current branch must be the task branch.
                    mode = str(project.settings.get("task_selection_mode", "directed"))
                    if mode == "directed":
                        if worktree_branch(project.repo_path) != current_task.branch_name:
                            raise OrchestratorError(
                                f"Expected to be on task branch {current_task.branch_name!r} "
                                f"but found {worktree_branch(project.repo_path)!r}."
                            )

            # ── Autonomous contract: require signal.task_started after first developer step ──
            mode = str(project.settings.get("task_selection_mode", "directed"))
            if mode == "autonomous" and current_task.created_by == "orchestrator":
                if current_task.id not in self._task_started_received:
                    if step_def.role not in {"_builtin:merge", "_builtin:mark_done"}:
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
                        self.store.save_task(current_task)
                        current_step = None
                        self._release_task_lease(current_task, project)
                        break

            visit_count = current_task.step_visit_counts.get(current_step, 0) + 1
            current_task.step_visit_counts[current_step] = visit_count
            self.store.save_task(current_task)

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
                self.store.save_task(current_task)
                break

            task_cost = sum(run.cost_usd for run in self.store.list_runs(task_id=current_task.id))
            cost_limit = _float_setting(
                project,
                "cost_limit_per_task_usd",
                default=None,
            )
            if cost_limit is not None and task_cost >= cost_limit:
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
                self.store.save_task(current_task)
                break

            sprint_cost_limit = _float_setting(
                project,
                "cost_limit_per_sprint_usd",
                default=None,
            )
            sprint_cost = float(
                self.store.run_totals(sprint_id=current_task.sprint_id)["total_cost_usd"]
            )
            if sprint_cost_limit is not None and sprint_cost >= sprint_cost_limit:
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
                self.store.save_task(current_task)
                break

            branch_sync_event: tuple[str, dict[str, Any]] | None = None
            if current_task.branch_name and step_def.role not in {
                "_builtin:merge",
                "_builtin:mark_done",
            }:
                checkout_branch(
                    project.repo_path,
                    current_task.branch_name,
                    create=True,
                    base_branch=project.default_branch,
                )
                (
                    carried_output,
                    branch_sync_event,
                ) = self._prepare_task_branch_for_step(
                    project=project,
                    task=current_task,
                    step=current_step,
                    carried_output=carried_output,
                )

            current_task.workflow_current_step = current_step
            current_task.workflow_carried_output = carried_output
            self.store.save_task(current_task)

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
                result = self.builtin_executor.execute(
                    step_def.role,
                    project=project,
                    task=current_task,
                    step_id=current_step,
                    carried_output=carried_output,
                    store=self.store,
                    event_recorder=lambda event_record: self._persist_builtin_event(run, event_record),
                )
                self.store.save_task(current_task)
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
                    {"step": current_step, "reason": "human_gate"},
                )
                return current_task

            if step_def.role.startswith("_builtin:"):
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
                result = self.builtin_executor.execute(
                    step_def.role,
                    project=project,
                    task=current_task,
                    step_id=current_step,
                    carried_output=carried_output,
                    store=self.store,
                )
                self.store.save_task(current_task)
                self._complete_run(
                    run,
                    status="completed",
                    outcome=result.outcome,
                    detail=result.detail,
                )
                self._emit_builtin_events(run, result.events)
                outcome = normalize_agent_outcome(result.outcome)
                detail = result.detail
            else:
                role = self.roles.get(step_def.role)
                if role is None:
                    raise OrchestratorError(f"Unknown role {step_def.role!r}.")
                current_task.assigned_role = role.id
                self.store.save_task(current_task)
                context_projection = build_project_context(
                    self.store,
                    project,
                    current_task=current_task,
                    carried_output=carried_output,
                )
                prompt = self._build_prompt(
                    role,
                    project,
                    current_task,
                    carried_output,
                    context_projection=context_projection,
                )
                model = role.agent.model or _string_setting(
                    project,
                    "default_model",
                    default="",
                )
                run = self._create_running_run(
                    current_task,
                    role_id=role.id,
                    workflow_step=current_step,
                    agent_backend=role.agent.backend,
                    model=model or None,
                    branch_name=current_task.branch_name,
                    prompt_text=prompt,
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
                self._emit_event(
                    run,
                    "workflow.step_started",
                    {"step": current_step, "visit_count": visit_count},
                )
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
                result = self._execute_agent_step(
                    role=role,
                    project=project,
                    task=current_task,
                    workflow_step=current_step,
                    prompt=prompt,
                    session_id=session_id,
                    carried_output=carried_output,
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
                    duration_ms=result.duration_ms,
                )
                retry_reason = self._output_contract_retry_reason(role, result)
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
                    retry_result = self._execute_agent_step(
                        role=role,
                        project=project,
                        task=current_task,
                        workflow_step=current_step,
                        prompt=retry_prompt,
                        session_id=retry_session_id,
                        carried_output=carried_output,
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
                        duration_ms=retry_result.duration_ms,
                    )
                    run = retry_run
                    result = retry_result
                if role.agent.session_persistence and result.session_id:
                    session_ids[session_key] = result.session_id
                outcome = normalize_agent_outcome(result.outcome)
                detail = result.detail

            self._emit_event(
                run,
                "workflow.step_completed",
                {"step": current_step, "outcome": outcome},
            )

            # ── After every step: verify default branch was not mutated.
            # Merge builtin intentionally changes the default branch — skip check.
            # If worktree is dirty (e.g. unresolved merge conflicts), skip to avoid
            # false positives from in-progress recovery workflows.
            if step_def.role != "_builtin:merge" and is_worktree_clean(project.repo_path):
                assert_default_branch_unchanged(
                    project.repo_path,
                    default_branch,
                    original_default_sha,
                )

            transition = workflow.find_transition(current_step, outcome)
            if transition is None:
                if current_task.status == "done":
                    current_task.workflow_current_step = None
                    current_task.workflow_carried_output = None
                    self.store.save_task(current_task)
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
                self.store.save_task(current_task)
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
            current_task.workflow_current_step = None
            current_task.workflow_carried_output = None
            self.store.save_task(current_task)
            current_step = transition.to_step

            # Renew lease after each step (heartbeat during workflow execution).
            if current_step is not None:
                self._renew_task_lease(current_task, project)

        return current_task

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

    def _safe_current_branch(self, repo_path: str) -> str | None:
        """Return the current branch name or None when git state is unavailable."""

        try:
            branch = current_branch(repo_path)
        except GitError:
            return None
        return branch or None

    def _restore_branch_if_safe(self, repo_path: str, branch_name: str | None) -> None:
        """Best-effort restore of the caller's branch when the worktree is clean."""

        if not branch_name:
            return
        try:
            active_branch = current_branch(repo_path)
            if active_branch == branch_name:
                return
            if not is_worktree_clean(repo_path):
                return
            checkout_branch(repo_path, branch_name)
        except GitError:
            return

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
            self.store.save_task(task)

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
                    "lease_token": task_lease.lease_token if task_lease else None,
                    "fencing_token": task_lease.fencing_token if task_lease else None,
                    "message": "Marked stale running run as failed.",
                },
            )

        task.status = "todo"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.step_visit_counts = {}
        self.store.save_task(task)
        self._restore_branch_if_safe(project.repo_path, project.default_branch)

    def _run_is_stale(self, project: Project, run: Run) -> bool:
        """Return whether a persisted running run has exceeded its allowed ownership window.

        A run is considered stale when:
        1. Its configured timeout has elapsed, AND
        2. The task's active lease is either missing or held by a different orchestrator
           (meaning the original holder is gone and the lease has expired).
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

        # Timeout has elapsed — check the task's active lease. If a live holder
        # holds the lease (different holder_id), the run is not ours to recover.
        task_lease = self.store.get_active_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=run.task_id,
        )
        if task_lease is not None and task_lease.holder_id != self.holder_id:
            # Another orchestrator holds an active lease — not stale.
            return False

        return True

    def prune_old_history(self, project: Project) -> dict[str, int]:
        """Prune old project history according to per-type retention settings.

        Reads three optional integer project settings:

        - ``event_retention_days`` — hard-delete old events (existing behavior)
        - ``run_retention_days`` — hard-delete old terminal runs and their events
        - ``prompt_retention_days`` — null out prompt_text on old terminal runs

        Each setting is independent.  Omitting a key disables that pruning type.
        Returns a dict with counts for each type that was actually pruned.
        """

        counts: dict[str, int] = {}

        event_days = _coerce_int_value(
            project.settings.get("event_retention_days"), default=None
        )
        if event_days is not None:
            cutoff = self._retention_cutoff(event_days)
            n = self.store.prune_old_events(project_id=project.id, older_than=cutoff)
            if n > 0:
                counts["events"] = n
                self._emit_pruned_event(project, "engine.event_pruned", n, cutoff)

        run_days = _coerce_int_value(
            project.settings.get("run_retention_days"), default=None
        )
        if run_days is not None:
            cutoff = self._retention_cutoff(run_days)
            n = self.store.prune_old_runs(project_id=project.id, older_than=cutoff)
            if n > 0:
                counts["runs"] = n
                self._emit_pruned_event(project, "engine.run_pruned", n, cutoff)

        prompt_days = _coerce_int_value(
            project.settings.get("prompt_retention_days"), default=None
        )
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
            if dependency.status not in {"done", "cancelled"}:
                return False
        return True

    def _build_prompt(
        self,
        role: RoleDefinition,
        project: Project,
        task: Task,
        carried_output: str | None,
        *,
        context_projection: ProjectContextProjection | None = None,
    ) -> str:
        latest_run = self.store.get_latest_run(task.id)
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
        if evidence is None and role.id in self.roles:
            evidence = self.build_completion_evidence(task, project)
            task.completion_evidence = evidence
            self.store.save_task(task)
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
            "git_status": self._safe_git_status(project.repo_path),
            "changed_files": self._safe_changed_files(
                project.repo_path,
                project.default_branch,
                task.branch_name,
            ),
            "recent_commits": self._safe_recent_commits(project.repo_path, task.branch_name),
            "completion_evidence": (
                str(evidence)
                if role.id == "code_reviewer" and task.branch_name and evidence is not None
                else ""
            ),
        }
        if evidence is not None:
            context.update({
                "completion_verdict": evidence.verdict,
                "completion_verdict_reasons": evidence.verdict_reasons,
                "completion_score": evidence.score,
                "completion_score_breakdown": evidence.score_breakdown,
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

    def _load_repo_instructions(self, repo_path: str) -> str:
        agents_path = Path(repo_path) / "AGENTS.md"
        if not agents_path.is_file():
            return ""
        return agents_path.read_text(encoding="utf-8")

    def _safe_git_status(self, repo_path: str) -> str:
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

        if (
            step != "develop"
            or not task.branch_name
            or not _is_merge_conflict_feedback(carried_output)
        ):
            return carried_output, None

        sync_result = sync_branch_with_base(
            project.repo_path,
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
                event_recorder=event_recorder,
            )
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
        event_recorder: Callable[[AgentEventRecord], None] | None = None,
    ) -> AgentExecutionResult:
        runner = self.agent_runners.get(role.agent.backend)
        if runner is None:
            raise OrchestratorError(
                f"No native runner is configured for backend {role.agent.backend!r}."
            )

        model = role.agent.model or _string_setting(
            project,
            "default_model",
            default="",
        )
        config = AgentRunConfig(
            backend=role.agent.backend,
            model=model or None,
            prompt=prompt,
            working_dir=Path(project.repo_path),
            session_id=session_id,
            permission_mode=role.agent.permission_mode,
            disallowed_tools=role.agent.tools.disallowed,
            extra_flags=role.agent.flags,
            timeout_seconds=_project_timeout_seconds(
                project,
                role_timeout_minutes=role.completion.timeout_minutes,
            ),
            max_cost_usd=max(role.completion.max_cost_usd, 0.0),
        )
        max_retries = _int_setting(project, "max_infra_retries", default=3)

        events: list[AgentEventRecord] = []
        message_fragments: list[str] = []
        final_status = "failed"
        outcome = "error"
        detail = ""
        final_session_id = session_id
        cost_usd = 0.0
        token_count = 0
        duration_ms: int | None = None

        retry_kwargs: dict[str, Any] = {"max_retries": max_retries}
        if self.runner_sleep is not None:
            retry_kwargs["sleep"] = self.runner_sleep

        for event in run_with_retry(
            runner,
            config,
            **retry_kwargs,
        ):
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
                duration_ms = _coerce_int_value(
                    event.payload.get("duration_ms"),
                    default=duration_ms,
                )
                outcome, detail = self._extract_completion_output(
                    role,
                    "\n\n".join(message_fragments),
                )
                final_status = "completed"
                continue

            if event.event_type == "agent.killed":
                gate_type = _optional_string(event.payload.get("gate_type")) or "gate"
                final_status = "timeout" if gate_type == "time" else "killed"
                outcome = "error"
                detail = (
                    _optional_string(event.payload.get("reason"))
                    or "Agent run was killed by a gate."
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
                duration_ms = _coerce_int_value(
                    event.payload.get("duration_ms"),
                    default=duration_ms,
                )
                final_status = "failed"
                detail = (
                    _optional_string(event.payload.get("error"))
                    or "\n\n".join(message_fragments)
                    or "Agent execution failed."
                )

        if not detail:
            detail = "\n\n".join(message_fragments).strip()
        if not detail:
            detail = "Agent execution finished without output."

        return AgentExecutionResult(
            outcome=outcome,
            detail=detail,
            status=final_status,
            session_id=final_session_id,
            cost_usd=cost_usd,
            token_count=token_count,
            duration_ms=duration_ms,
            model=model or None,
            events=tuple(events),
            events_streamed=event_recorder is not None,
        )

    def _extract_completion_output(
        self,
        role: RoleDefinition,
        text: str,
    ) -> tuple[str, str]:
        cleaned_text = text.strip()
        output_config = role.completion.output
        marker = role.completion.marker.strip()

        if output_config.extract_decision:
            return _extract_decision_output(cleaned_text)

        if marker:
            if not _contains_completion_marker(cleaned_text, marker):
                return (ERROR, f"Missing completion marker `{marker}`.")
            cleaned_text = _strip_completion_marker(cleaned_text, marker)

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
            correction = (
                "Your previous response did not follow the required final output format.\n"
                "Do not do more review work.\n"
                "Return exactly one line and nothing else:\n"
                "APPROVE\n"
                "DENY: <reason>\n"
                "STEER: <specific corrective action>"
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
            self._apply_agent_signal(task, project, role_id, event_record)

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
        self._apply_agent_signal(task, project, role_id, event_record)

    def _apply_agent_signal(
        self,
        task: Task,
        project: Project,
        role_id: str,
        event_record: AgentEventRecord,
    ) -> None:
        payload = event_record.payload
        if event_record.event_type == "signal.task_started":
            task.title = str(payload.get("title", task.title))
            task.task_type = str(payload.get("task_type", task.task_type))
            task.branch_name = str(payload.get("branch", task.branch_name or "")) or task.branch_name
            task.acceptance_criteria = str(
                payload.get("criteria", task.acceptance_criteria or "")
            ) or task.acceptance_criteria
            self.store.save_task(task)
            self._task_started_received.add(task.id)
            return

        if event_record.event_type == "signal.task_created":
            sprint = self.store.get_active_sprint(project.id)
            if sprint is None:
                return
            order_index = self.store.next_task_order_index(sprint.id)
            created_task = Task(
                id=_new_id("task"),
                sprint_id=sprint.id,
                project_id=project.id,
                title=str(payload.get("title", "(agent-created task)")),
                task_type=str(payload.get("task_type", "feature")),
                description=_optional_string(payload.get("description")),
                acceptance_criteria=_optional_string(payload.get("criteria")),
                order_index=order_index,
                created_by=f"agent:{role_id}",
                created_at=event_record.timestamp,
            )
            self.store.save_task(created_task)
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
                self.store.save_task(task)
                self._release_task_lease(task, project)

    def _emit_builtin_events(
        self,
        run: Run,
        events: tuple[BuiltinEventRecord, ...],
    ) -> None:
        for event_record in events:
            self._emit_event(run, event_record.event_type, event_record.payload)

    def _persist_builtin_event(
        self,
        run: Run,
        event_record: BuiltinEventRecord,
    ) -> None:
        """Persist one builtin event immediately while the builtin step is active."""

        self._emit_event(run, event_record.event_type, event_record.payload)

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
        return run

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
        duration_ms: int | None = None,
    ) -> None:
        run.status = status
        run.outcome = outcome
        run.outcome_detail = detail
        run.model = model
        run.session_id = session_id
        if cost_usd is not None:
            run.cost_usd = cost_usd
        if token_count is not None:
            run.token_count = token_count
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
        return event


def generate_branch_name(task: Task) -> str:
    """Generate a stable branch name for one directed task."""

    prefix = _BRANCH_PREFIXES.get(task.task_type, "feat")
    return f"{prefix}/{task.id}"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


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


def _extract_decision_output(text: str) -> tuple[str, str]:
    if not text:
        return (ERROR, "Reviewer returned no decision.")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for raw_line in reversed(lines):
        line = _normalize_decision_line(raw_line)
        if line == "APPROVE":
            return (APPROVE, "APPROVE")
        if line == "DENY":
            return (DENY, "DENY")
        if line == "STEER":
            return (STEER, "STEER")
        if line.startswith("DENY:"):
            return (DENY, line.partition(":")[2].strip() or text)
        if line.startswith("STEER:"):
            return (STEER, line.partition(":")[2].strip() or text)
        if line.startswith("APPROVE:"):
            return (APPROVE, line.partition(":")[2].strip() or text)
    return (ERROR, text)


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
