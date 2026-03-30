"""Task orchestration for Foreman workflow execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Protocol
from uuid import uuid4

from .builtins import BuiltinEventRecord, BuiltinExecutor
from .context import ProjectContextProjection, build_project_context, relative_project_path
from .errors import ForemanError
from .git import GitError, changed_files, checkout_branch, recent_commits, status_text
from .models import Event, Project, Run, Task, utc_now_text
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
            else {"claude_code": ClaudeCodeRunner(), "codex": CodexRunner()}
        )
        self.builtin_executor = builtin_executor or BuiltinExecutor()
        self.runner_sleep = runner_sleep

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
        self.recover_orphaned_tasks(project.id)

        executed_task_ids: list[str] = []
        blocked_task_ids: list[str] = []
        if task_id is not None:
            task = self.store.get_task(task_id)
            if task is None or task.project_id != project.id:
                raise OrchestratorError(
                    f"Task {task_id!r} does not belong to project {project.id!r}."
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

        while True:
            task = self.select_next_task(project)
            if task is None:
                break
            completed = self.run_task(project, workflow, task)
            executed_task_ids.append(completed.id)
            if completed.status == "blocked":
                blocked_task_ids.append(completed.id)

        active_sprint = self.store.get_active_sprint(project.id)
        remaining = (
            self.store.list_tasks(sprint_id=active_sprint.id)
            if active_sprint is not None
            else []
        )
        if any(task.status == "blocked" for task in remaining):
            stop_reason = "blocked"
        elif any(task.status in {"todo", "in_progress"} for task in remaining):
            stop_reason = "waiting"
        else:
            stop_reason = "idle"
        return ProjectRunResult(
            project_id=project.id,
            executed_task_ids=tuple(executed_task_ids),
            blocked_task_ids=tuple(blocked_task_ids),
            stop_reason=stop_reason,
        )

    def select_next_task(self, project: Project) -> Task | None:
        """Return the next runnable task for one project."""

        selection_mode = str(project.settings.get("task_selection_mode", "directed"))
        if selection_mode != "directed":
            raise OrchestratorError(
                f"Task selection mode {selection_mode!r} is not implemented yet."
            )

        sprint = self.store.get_active_sprint(project.id)
        if sprint is None:
            return None
        sprint_tasks = self.store.list_tasks(sprint_id=sprint.id)
        tasks_by_id = {task.id: task for task in sprint_tasks}
        for task in sprint_tasks:
            if task.status == "in_progress" and task.workflow_current_step:
                return task
        for task in sprint_tasks:
            if task.status != "todo":
                continue
            if self._dependencies_satisfied(task, tasks_by_id):
                return task
        return None

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

    def resume_human_gate(
        self,
        task_id: str,
        *,
        outcome: str,
        note: str | None = None,
    ) -> HumanGateResumeResult:
        """Apply one human-gate decision and continue execution when possible."""

        if outcome not in {"approve", "deny"}:
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
        deferred = (
            not next_step.role.startswith("_builtin:")
            and self.agent_executor is None
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
        session_id: str | None = None

        while current_step is not None:
            step_def = workflow.get_step(current_step)
            if step_def is None:
                raise OrchestratorError(
                    f"Workflow {workflow.id!r} is missing step {current_step!r}."
                )

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
                outcome = result.outcome
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
                    "workflow.step_started",
                    {"step": current_step, "visit_count": visit_count},
                )
                result = self._execute_agent_step(
                    role=role,
                    project=project,
                    task=current_task,
                    workflow_step=current_step,
                    prompt=prompt,
                    session_id=session_id if role.agent.session_persistence else None,
                    carried_output=carried_output,
                )
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
                if role.agent.session_persistence and result.session_id:
                    session_id = result.session_id
                outcome = result.outcome
                detail = result.detail

            self._emit_event(
                run,
                "workflow.step_completed",
                {"step": current_step, "outcome": outcome},
            )

            transition = workflow.find_transition(current_step, outcome)
            if transition is None:
                if current_task.status == "done":
                    current_task.workflow_current_step = None
                    current_task.workflow_carried_output = None
                    self.store.save_task(current_task)
                    current_step = None
                    break

                self._emit_event(
                    run,
                    "workflow.no_transition",
                    {"step": current_step, "outcome": outcome},
                )
                current_task.status = "blocked"
                current_task.blocked_reason = (
                    workflow.fallback.message
                    if workflow.fallback is not None
                    else f"No transition for '{outcome}' at '{current_step}'"
                )
                current_task.workflow_current_step = None
                current_task.workflow_carried_output = None
                self.store.save_task(current_task)
                current_step = None
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
            current_task.workflow_current_step = None
            current_task.workflow_carried_output = None
            self.store.save_task(current_task)
            current_step = transition.to_step

        return current_task

    def recover_orphaned_tasks(self, project_id: str) -> None:
        """Reset orphaned in-progress tasks after a prior engine crash."""

        orphaned_tasks = self.store.list_tasks(project_id=project_id, status="in_progress")
        for task in orphaned_tasks:
            if task.workflow_current_step is not None:
                continue

            active_runs = self.store.list_runs(task_id=task.id, status="running")
            for run in active_runs:
                run.status = "failed"
                run.outcome = "error"
                run.outcome_detail = "Engine crashed during run"
                run.completed_at = utc_now_text()
                self.store.save_run(run)
                self._emit_event(
                    run,
                    "engine.crash_recovery",
                    {
                        "task_id": task.id,
                        "message": "Marked interrupted run as failed.",
                    },
                )

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
        }
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
            timeout_seconds=max(role.completion.timeout_minutes, 0) * 60,
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
            events.append(
                AgentEventRecord(
                    event_type=event.event_type,
                    payload=dict(event.payload),
                    timestamp=event.timestamp,
                )
            )
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
            if marker not in cleaned_text.splitlines():
                return ("error", f"Missing completion marker `{marker}`.")
            cleaned_text = _strip_completion_marker(cleaned_text, marker)

        if output_config.extract_json:
            json_block = _extract_json_block(cleaned_text)
            return ("done", json_block or cleaned_text or "Completed without JSON output.")

        if output_config.extract_summary or output_config.extract_branch:
            return ("done", cleaned_text or "Completed.")

        return ("done", cleaned_text or "Completed.")

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
            return

        if event_record.event_type == "signal.task_created":
            sprint = self.store.get_active_sprint(project.id)
            if sprint is None:
                return
            created_task = Task(
                id=_new_id("task"),
                sprint_id=sprint.id,
                project_id=project.id,
                title=str(payload.get("title", "(agent-created task)")),
                task_type=str(payload.get("task_type", "feature")),
                description=_optional_string(payload.get("description")),
                acceptance_criteria=_optional_string(payload.get("criteria")),
                created_by=f"agent:{role_id}",
                created_at=event_record.timestamp,
            )
            self.store.save_task(created_task)
            return

        if event_record.event_type == "signal.blocker":
            message = _optional_string(payload.get("message"))
            if message:
                task.status = "blocked"
                task.blocked_reason = message
                self.store.save_task(task)

    def _emit_builtin_events(
        self,
        run: Run,
        events: tuple[BuiltinEventRecord, ...],
    ) -> None:
        for event_record in events:
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
    slug = _slugify(task.title)
    if slug:
        return f"{prefix}/{task.id}-{slug}"
    return f"{prefix}/{task.id}"


def _slugify(text: str) -> str:
    lowered = text.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:48]


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


def _extract_decision_output(text: str) -> tuple[str, str]:
    if not text:
        return ("error", "Reviewer returned no decision.")

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line == "APPROVE":
        return ("approve", "APPROVE")
    if first_line == "DENY":
        return ("deny", "DENY")
    if first_line == "STEER":
        return ("steer", "STEER")
    if first_line.startswith("DENY:"):
        return ("deny", first_line.partition(":")[2].strip() or text)
    if first_line.startswith("STEER:"):
        return ("steer", first_line.partition(":")[2].strip() or text)
    if first_line.startswith("APPROVE:"):
        return ("approve", first_line.partition(":")[2].strip() or text)
    return ("error", text)


def _strip_completion_marker(text: str, marker: str) -> str:
    lines = [line for line in text.splitlines() if line.strip() != marker]
    return "\n".join(lines).strip()


def _extract_json_block(text: str) -> str | None:
    match = re.search(r"```json\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match is None:
        return None
    return match.group(1).strip() or None

