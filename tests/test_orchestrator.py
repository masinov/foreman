"""Integration coverage for the persisted Foreman orchestrator loop."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.models import Event, Project, Run, Sprint, Task
from foreman.orchestrator import (
    AgentExecutionResult,
    ForemanOrchestrator,
    OrchestratorError,
    _extract_decision_output,
)
from foreman.git import current_branch
from foreman.runner.base import AgentEvent, AgentRunConfig, InfrastructureError, PreflightError
from foreman.roles import default_roles_dir, load_roles
from foreman.store import ForemanStore
from foreman.workflows import (
    WorkflowDefinition,
    WorkflowFallback,
    WorkflowStep,
    WorkflowTransition,
    default_workflows_dir,
    load_workflows,
)


@dataclass(slots=True)
class PromptCapture:
    """Recorded prompt input for one scripted agent call."""

    role_id: str
    call_index: int
    workflow_step: str
    carried_output: str | None
    prompt: str
    branch_name: str | None


class ScriptedAgentExecutor:
    """Drive agent steps with deterministic scripted behavior."""

    def __init__(self, handlers: dict[tuple[str, int], object]) -> None:
        self.handlers = handlers
        self.call_counts: dict[str, int] = {}
        self.captures: list[PromptCapture] = []

    def execute(
        self,
        *,
        role,
        project,
        task,
        workflow_step: str,
        prompt: str,
        session_id: str | None,
        carried_output: str | None,
    ) -> AgentExecutionResult:
        del project
        del session_id
        call_index = self.call_counts.get(role.id, 0) + 1
        self.call_counts[role.id] = call_index
        self.captures.append(
            PromptCapture(
                role_id=role.id,
                call_index=call_index,
                workflow_step=workflow_step,
                carried_output=carried_output,
                prompt=prompt,
                branch_name=task.branch_name,
            )
        )
        handler = self.handlers.get((role.id, call_index))
        if handler is None:
            raise AssertionError(f"No scripted handler for {(role.id, call_index)!r}")
        return handler(task=task, prompt=prompt, carried_output=carried_output)

    def capture(self, role_id: str, call_index: int) -> PromptCapture:
        for capture in self.captures:
            if capture.role_id == role_id and capture.call_index == call_index:
                return capture
        raise AssertionError(f"Missing prompt capture for {(role_id, call_index)!r}")


@dataclass(slots=True)
class RunnerCapture:
    """Recorded native runner input for one orchestrated call."""

    call_index: int
    model: str | None
    session_id: str | None
    prompt: str
    working_dir: Path
    disallowed_tools: tuple[str, ...]
    timeout_seconds: int


class ScriptedNativeRunner:
    """Drive the native runner path with deterministic scripted behavior."""

    def __init__(self, handlers: dict[int, object]) -> None:
        self.handlers = handlers
        self.call_count = 0
        self.captures: list[RunnerCapture] = []

    def run(self, config: AgentRunConfig):
        self.call_count += 1
        self.captures.append(
            RunnerCapture(
                call_index=self.call_count,
                model=config.model,
                session_id=config.session_id,
                prompt=config.prompt,
                working_dir=config.working_dir,
                disallowed_tools=config.disallowed_tools,
                timeout_seconds=config.timeout_seconds,
            )
        )
        handler = self.handlers.get(self.call_count)
        if handler is None:
            raise AssertionError(f"No scripted native runner handler for call {self.call_count}")
        if isinstance(handler, Exception):
            raise handler
        yield from handler(config)

    def capture(self, call_index: int) -> RunnerCapture:
        for capture in self.captures:
            if capture.call_index == call_index:
                return capture
        raise AssertionError(f"Missing native runner capture for call {call_index}")


class ForemanOrchestratorTests(unittest.TestCase):
    """Verify that the orchestrator can drive the shipped development workflow."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.roles = load_roles(default_roles_dir())
        cls.workflows = load_workflows(
            default_workflows_dir(),
            available_role_ids=set(cls.roles),
        )

    def create_workspace(self) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo_path = root / "repo"
        repo_path.mkdir()
        db_path = root / "foreman.db"
        return repo_path, db_path

    def git(self, repo_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)} failed in {repo_path}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit_all(self, repo_path: Path, message: str) -> None:
        self.git(repo_path, "add", ".")
        self.git(repo_path, "commit", "-m", message)

    def initialize_repo(self, repo_path: Path) -> None:
        self.git(repo_path, "init")
        self.git(repo_path, "checkout", "-b", "main")
        self.git(repo_path, "config", "user.email", "foreman-tests@example.com")
        self.git(repo_path, "config", "user.name", "Foreman Tests")
        self.write_text(repo_path / "AGENTS.md", "# Local Instructions\nUse tests.\n")
        self.write_text(repo_path / ".gitignore", ".foreman/\n")
        self.write_text(repo_path / "README.md", "# Temp Repo\n")
        self.commit_all(repo_path, "chore: initial commit")

    def seed_project(
        self,
        store: ForemanStore,
        *,
        repo_path: Path,
        workflow_id: str = "development",
        task_title: str = "Implement orchestrator loop",
        test_command: str = "test -f ready.txt",
        branch_name: str | None = None,
        acceptance_criteria: str | None = "Task reaches done after review, test, and merge.",
    ) -> tuple[Project, Sprint, Task]:
        project = Project(
            id="project-1",
            name="Foreman Demo",
            repo_path=str(repo_path),
            spec_path="docs/specs/engine-design-v3.md",
            workflow_id=workflow_id,
            default_branch="main",
            settings={
                "task_selection_mode": "directed",
                "test_command": test_command,
                "default_model": "gpt-5.4",
                "max_step_visits": 5,
            },
            created_at="2026-03-30T12:00:00Z",
            updated_at="2026-03-30T12:00:00Z",
        )
        sprint = Sprint(
            id="sprint-1",
            project_id=project.id,
            title="Orchestrator",
            goal="Run a task through the development workflow",
            status="active",
            order_index=1,
            created_at="2026-03-30T12:05:00Z",
            started_at="2026-03-30T12:10:00Z",
        )
        task = Task(
            id="task-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title=task_title,
            description="Drive the standard workflow from the store.",
            status="todo",
            task_type="feature",
            priority=1,
            order_index=1,
            acceptance_criteria=acceptance_criteria,
            created_at="2026-03-30T12:15:00Z",
        )
        task.branch_name = branch_name
        store.save_project(project)
        store.save_sprint(sprint)
        store.save_task(task)
        return project, sprint, task

    def seed_run(
        self,
        store: ForemanStore,
        *,
        project: Project,
        task: Task,
        role_id: str,
        workflow_step: str,
        agent_backend: str,
        created_at: str,
        session_id: str | None = None,
        outcome: str = "done",
        outcome_detail: str = "Completed.",
        status: str = "completed",
        model: str | None = None,
    ) -> Run:
        run = Run(
            id=f"run-{len(store.list_runs(task_id=task.id)) + 1}",
            task_id=task.id,
            project_id=project.id,
            role_id=role_id,
            workflow_step=workflow_step,
            agent_backend=agent_backend,
            status=status,
            outcome=outcome,
            outcome_detail=outcome_detail,
            model=model,
            session_id=session_id,
            branch_name=task.branch_name,
            created_at=created_at,
        )
        store.save_run(run)
        return run

    def roles_with_backend(
        self,
        backend: str,
        *,
        role_models: dict[str, str] | None = None,
    ) -> dict[str, object]:
        role_models = role_models or {}
        updated_roles = {}
        for role_id, role in self.roles.items():
            updated_roles[role_id] = replace(
                role,
                agent=replace(
                    role.agent,
                    backend=backend,
                    model=role_models.get(role_id, role.agent.model),
                ),
            )
        return updated_roles

    def test_run_project_advances_one_task_through_the_shipped_workflow(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("Task: Implement orchestrator loop", prompt)
                self.assertIn("Branch: feat/task-1", prompt)
                self.write_text(repo_path / "feature.txt", "implemented\n")
                self.write_text(repo_path / "ready.txt", "ready\n")
                self.commit_all(repo_path, "feat: implement workflow slice")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the workflow slice.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Implemented the workflow slice.", prompt)
                self.assertIn("feature.txt", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after review.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                    }
                ),
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.blocked_task_ids, ())

            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.branch_name,
                "feat/task-1",
            )
            self.assertIsNotNone(updated_task.completed_at)
            self.assertEqual(current_branch(repo_path), "main")

            runs = store.list_runs(task_id=task.id)
            agent_runs = [r for r in runs if r.role_id != "_builtin:orchestrator"]
            self.assertEqual(
                [r.workflow_step for r in agent_runs],
                ["develop", "review", "test", "merge", "done"],
            )
            self.assertEqual(
                [r.outcome for r in agent_runs],
                ["done", "approve", "success", "success", "success"],
            )

            event_types = [event.event_type for event in store.list_events(task_id=task.id)]
            self.assertIn("engine.test_run", event_types)
            self.assertIn("engine.merge", event_types)
            self.assertIn("workflow.transition", event_types)
            self.assertNotIn("workflow.no_transition", event_types)

        self.assertTrue((repo_path / "feature.txt").is_file())
        self.assertTrue((repo_path / "ready.txt").is_file())
        self.assertEqual(
            self.git(repo_path, "branch", "--show-current").stdout.strip(),
            "main",
        )

    def test_secure_workflow_runs_through_security_review_and_finishes_task(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_secure",
                task_title="Ship secure workflow slice",
            )
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Task: Ship secure workflow slice", prompt)
                self.write_text(repo_path / "feature.txt", "secure implementation\n")
                self.write_text(repo_path / "ready.txt", "ready\n")
                self.commit_all(repo_path, "feat: implement secure workflow slice")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the secure workflow slice.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Implemented the secure workflow slice.", prompt)
                self.assertIn("feature.txt", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved for security review.",
                )

            def security_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Inspect the code changes on branch", prompt)
                self.assertIn("feature.txt", prompt)
                self.assertIn("ready.txt", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="No security issues found.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                        ("security_reviewer", 1): security_handler,
                    }
                ),
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.blocked_task_ids, ())
            self.assertEqual(result.stop_reason, "idle")

            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.step_visit_counts,
                {
                    "develop": 1,
                    "code_review": 1,
                    "security_review": 1,
                    "test": 1,
                    "merge": 1,
                    "done": 1,
                },
            )

            runs = store.list_runs(task_id=task.id)
            agent_runs = [r for r in runs if r.role_id != "_builtin:orchestrator"]
            self.assertEqual(
                [r.workflow_step for r in agent_runs],
                ["develop", "code_review", "security_review", "test", "merge", "done"],
            )
            self.assertEqual(
                [r.outcome for r in agent_runs],
                ["done", "approve", "approve", "success", "success", "success"],
            )

            transitions = [
                event.payload
                for event in store.list_events(task_id=task.id)
                if event.event_type == "workflow.transition"
            ]
            self.assertIn(
                {
                    "from_step": "code_review",
                    "to_step": "security_review",
                    "trigger": "completion:approve",
                },
                transitions,
            )
            self.assertIn(
                {
                    "from_step": "security_review",
                    "to_step": "test",
                    "trigger": "completion:approve",
                },
                transitions,
            )

    def test_security_review_denial_carries_output_back_into_development(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_secure",
                task_title="Remove insecure token handling",
            )
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            executor = ScriptedAgentExecutor({})

            def developer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.write_text(repo_path / "feature.txt", "token = 'hardcoded'\n")
                self.write_text(repo_path / "ready.txt", "ready\n")
                self.commit_all(repo_path, "feat: initial secure workflow implementation")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Initial implementation complete.",
                )

            def reviewer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Initial implementation complete.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved for security review.",
                )

            def security_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("feature.txt", prompt)
                return AgentExecutionResult(
                    outcome="deny",
                    detail="Remove the hardcoded token in feature.txt.",
                )

            def developer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertEqual(
                    carried_output,
                    "Remove the hardcoded token in feature.txt.",
                )
                self.assertIn("Remove the hardcoded token in feature.txt.", prompt)
                self.write_text(repo_path / "feature.txt", "token = os.environ['TOKEN']\n")
                self.commit_all(repo_path, "fix: remove hardcoded token")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Removed the hardcoded token.",
                )

            def reviewer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Removed the hardcoded token.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after security fix.",
                )

            def security_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("feature.txt", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Security review passed.",
                )

            executor.handlers.update(
                {
                    ("developer", 1): developer_one,
                    ("code_reviewer", 1): reviewer_one,
                    ("security_reviewer", 1): security_one,
                    ("developer", 2): developer_two,
                    ("code_reviewer", 2): reviewer_two,
                    ("security_reviewer", 2): security_two,
                }
            )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "idle")

            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.step_visit_counts,
                {
                    "develop": 2,
                    "code_review": 2,
                    "security_review": 2,
                    "test": 1,
                    "merge": 1,
                    "done": 1,
                },
            )
            self.assertEqual(
                executor.capture("developer", 2).carried_output,
                "Remove the hardcoded token in feature.txt.",
            )
            self.assertEqual(
                [
                    r.workflow_step
                    for r in store.list_runs(task_id=task.id)
                    if r.role_id != "_builtin:orchestrator"
                ],
                [
                    "develop",
                    "code_review",
                    "security_review",
                    "develop",
                    "code_review",
                    "security_review",
                    "test",
                    "merge",
                    "done",
                ],
            )

            transitions = [
                event.payload
                for event in store.list_events(task_id=task.id)
                if event.event_type == "workflow.transition"
            ]
            self.assertIn(
                {
                    "from_step": "security_review",
                    "to_step": "develop",
                    "trigger": "completion:deny",
                },
                transitions,
            )

    def test_review_feedback_and_test_failures_carry_output_back_into_development(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            executor = ScriptedAgentExecutor({})

            def developer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("Branch: feat/task-1", prompt)
                self.write_text(repo_path / "feature.txt", "initial implementation\n")
                self.commit_all(repo_path, "feat: initial implementation")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Initial implementation complete.",
                )

            def reviewer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Initial implementation complete.", prompt)
                return AgentExecutionResult(
                    outcome="deny",
                    detail="Please add the ready marker.",
                )

            def developer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertEqual(carried_output, "Please add the ready marker.")
                self.assertIn("Please add the ready marker.", prompt)
                self.write_text(repo_path / "feature.txt", "updated after review\n")
                self.commit_all(repo_path, "feat: address review guidance")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Updated after review feedback.",
                )

            def reviewer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Updated after review feedback.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved for testing.",
                )

            def developer_three(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertEqual(carried_output, "Command exited with 1.")
                self.assertIn("Command exited with 1.", prompt)
                self.write_text(repo_path / "ready.txt", "ready now\n")
                self.commit_all(repo_path, "fix: add ready marker")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Added the ready marker after test failure.",
                )

            def reviewer_three(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Added the ready marker after test failure.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after the test fix.",
                )

            executor.handlers.update(
                {
                    ("developer", 1): developer_one,
                    ("code_reviewer", 1): reviewer_one,
                    ("developer", 2): developer_two,
                    ("code_reviewer", 2): reviewer_two,
                    ("developer", 3): developer_three,
                    ("code_reviewer", 3): reviewer_three,
                }
            )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.step_visit_counts,
                {
                    "develop": 3,
                    "review": 3,
                    "test": 2,
                    "merge": 1,
                    "done": 1,
                },
            )

            self.assertEqual(
                [
                    r.workflow_step
                    for r in store.list_runs(task_id=task.id)
                    if r.role_id != "_builtin:orchestrator"
                ],
                [
                    "develop",
                    "review",
                    "develop",
                    "review",
                    "test",
                    "develop",
                    "review",
                    "test",
                    "merge",
                    "done",
                ],
            )
            self.assertEqual(
                executor.capture("developer", 2).carried_output,
                "Please add the ready marker.",
            )
            self.assertEqual(
                executor.capture("developer", 3).carried_output,
                "Command exited with 1.",
            )

            events = store.list_events(task_id=task.id)
            transitions = [
                event.payload
                for event in events
                if event.event_type == "workflow.transition"
            ]
            self.assertIn(
                {
                    "from_step": "review",
                    "to_step": "develop",
                    "trigger": "completion:deny",
                },
                transitions,
            )
            self.assertIn(
                {
                    "from_step": "test",
                    "to_step": "develop",
                    "trigger": "completion:failure",
                },
                transitions,
            )

    def test_human_gate_approve_resumes_workflow_and_finishes_the_task(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_with_architect",
                task_title="Approve the architect plan",
                branch_name="feat/task-1",
            )
            executor = ScriptedAgentExecutor({})

            def architect_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Title: Approve the architect plan", prompt)
                self.write_text(repo_path / "plan.md", "Initial plan\n")
                self.commit_all(repo_path, "docs: capture initial plan")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Architect plan ready for approval.",
                )

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("## Task: Approve the architect plan", prompt)
                self.write_text(repo_path / "plan.md", "approved plan\n")
                # Commit concrete files on the branch; file names contain keywords
                # from the task acceptance criteria "Task reaches done after review,
                # test, and merge." so the completion guard can score them.
                (repo_path / "plan_review.py").write_text("def review(): pass\n")
                (repo_path / "plan_test.py").write_text("def test(): pass\n")
                (repo_path / "plan_merge.py").write_text("def merge(): pass\n")
                (repo_path / "ready.txt").write_text("ok\n")
                self.commit_all(repo_path, "feat: implement approved plan")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the approved plan.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Implemented the approved plan.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after review.",
                )

            executor.handlers.update(
                {
                    ("architect", 1): architect_handler,
                    ("developer", 1): developer_handler,
                    ("code_reviewer", 1): reviewer_handler,
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            first_result = orchestrator.run_project(project.id)

            self.assertEqual(first_result.executed_task_ids, (task.id,))
            self.assertEqual(first_result.blocked_task_ids, (task.id,))

            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )
            resume_result = resume_orchestrator.resume_human_gate(
                task.id,
                outcome="approve",
                note="looks good",
            )

            self.assertFalse(resume_result.deferred)
            self.assertEqual(resume_result.paused_step, "human_approval")
            self.assertEqual(resume_result.next_step, "develop")
            self.assertEqual(resume_result.task.status, "done")
            self.assertIsNone(resume_result.task.workflow_current_step)

            runs = store.list_runs(task_id=task.id)
            self.assertEqual(
                [run.workflow_step for run in runs if run.role_id != "_builtin:orchestrator"],
                ["plan", "human_approval", "human_approval", "develop", "review", "test", "merge", "done"],
            )
            self.assertEqual(
                [run.outcome for run in runs],
                ["done", "paused", "approve", "done", "approve", "success", "success", "success"],
            )

            resumed_events = [
                event.payload
                for event in store.list_events(task_id=task.id)
                if event.event_type == "workflow.resumed"
            ]
            self.assertEqual(
                resumed_events,
                [
                    {
                        "step": "human_approval",
                        "decision": "approve",
                        "next_step": "develop",
                        "deferred": False,
                        "note": "looks good",
                    }
                ],
            )

    def test_human_gate_deny_carries_the_note_back_into_planning(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_with_architect",
                task_title="Rework the architect plan",
            )
            executor = ScriptedAgentExecutor({})

            def architect_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.write_text(repo_path / "plan.md", "Initial plan\n")
                self.commit_all(repo_path, "docs: draft initial plan")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Initial plan ready.",
                )

            def architect_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertEqual(carried_output, "rethink the approach")
                self.assertIn("rethink the approach", prompt)
                self.write_text(repo_path / "plan.md", "Revised plan\n")
                self.commit_all(repo_path, "docs: revise plan after denial")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Revised plan ready.",
                )

            executor.handlers.update(
                {
                    ("architect", 1): architect_one,
                    ("architect", 2): architect_two,
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            first_result = orchestrator.run_project(project.id)

            self.assertEqual(first_result.stop_reason, "blocked")
            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )
            resume_result = resume_orchestrator.resume_human_gate(
                task.id,
                outcome="deny",
                note="rethink the approach",
            )

            self.assertFalse(resume_result.deferred)
            self.assertEqual(resume_result.next_step, "plan")
            self.assertEqual(resume_result.task.status, "blocked")
            self.assertEqual(resume_result.task.workflow_current_step, "human_approval")
            self.assertEqual(
                resume_result.task.step_visit_counts,
                {"plan": 2, "human_approval": 2},
            )

            runs = store.list_runs(task_id=task.id)
            self.assertEqual(
                [run.workflow_step for run in runs if run.role_id != "_builtin:orchestrator"],
                ["plan", "human_approval", "human_approval", "plan", "human_approval"],
            )
            self.assertEqual(
                [run.outcome for run in runs],
                ["done", "paused", "deny", "done", "paused"],
            )

    def test_human_gate_resume_defers_when_the_next_backend_is_unavailable(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_with_architect",
                task_title="Resume after bootstrap approval",
                branch_name="feat/task-1-resume-after-bootstrap-approval",
            )
            blocked_task = Task(
                id=task.id,
                sprint_id=task.sprint_id,
                project_id=task.project_id,
                title=task.title,
                description=task.description,
                status="blocked",
                task_type=task.task_type,
                priority=task.priority,
                order_index=task.order_index,
                acceptance_criteria=task.acceptance_criteria,
                blocked_reason="Awaiting human approval",
                workflow_current_step="human_approval",
                created_at=task.created_at,
                started_at="2026-03-30T12:20:00Z",
            )
            store.save_task(blocked_task)
            unavailable_roles = self.roles_with_backend("missing_backend")

            bootstrap_orchestrator = ForemanOrchestrator(
                store,
                roles=unavailable_roles,
                workflows=self.workflows,
            )
            resume_result = bootstrap_orchestrator.resume_human_gate(
                task.id,
                outcome="approve",
            )

            self.assertTrue(resume_result.deferred)
            self.assertEqual(resume_result.task.status, "in_progress")
            self.assertEqual(resume_result.task.workflow_current_step, "develop")
            self.assertIsNone(resume_result.task.blocked_reason)

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.write_text(repo_path / "feature.txt", "implemented after defer\n")
                self.write_text(repo_path / "ready.txt", "ready\n")
                self.write_text(repo_path / "deferred_task.py", "def done(): pass\n")
                self.commit_all(repo_path, "feat: finish deferred task")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Finished after deferred resume.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIn("Finished after deferred resume.", prompt)
                self.assertIsNone(carried_output)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after deferred resume.",
                )

            runner_orchestrator = ForemanOrchestrator(
                store,
                roles=unavailable_roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                    }
                ),
            )

            result = runner_orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "idle")
            final_task = store.get_task(task.id)
            self.assertIsNotNone(final_task)
            assert final_task is not None
            self.assertEqual(final_task.status, "done")

    def test_native_runner_executes_claude_roles_without_an_injected_executor(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            store.save_project(project)
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(repo_path, config),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "idle")
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

            developer_capture = runner.capture(1)
            reviewer_capture = runner.capture(2)
            self.assertEqual(developer_capture.model, "claude-sonnet-4-6")
            self.assertIsNone(developer_capture.session_id)
            self.assertEqual(reviewer_capture.disallowed_tools, ("Bash", "Write", "Edit", "NotebookEdit"))

            runs = store.list_runs(task_id=task.id)
            workflow_runs = [r for r in runs if r.role_id != "_builtin:orchestrator"]
            self.assertEqual(
                [run.workflow_step for run in workflow_runs],
                ["develop", "review", "test", "merge", "done"],
            )
            self.assertEqual(workflow_runs[0].session_id, "dev-session")
            self.assertEqual(
                [run.outcome for run in workflow_runs],
                ["done", "approve", "success", "success", "success"],
            )

    def test_native_runner_reuses_persistent_developer_sessions_after_review_denial(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_initial_pass(repo_path, config),
                    2: lambda config: self._native_reviewer_deny(config),
                    3: lambda config: self._native_developer_followup(repo_path, config),
                    4: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(runner.capture(1).session_id, None)
            self.assertEqual(runner.capture(3).session_id, "dev-session")
            self.assertIn("Please add the ready marker.", runner.capture(3).prompt)

            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.step_visit_counts,
                {
                    "develop": 2,
                    "review": 2,
                    "test": 1,
                    "merge": 1,
                    "done": 1,
                },
            )

    def test_native_runner_reuses_persisted_claude_session_after_fresh_orchestrator_invocation(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            task.status = "in_progress"
            task.workflow_current_step = "develop"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                session_id="persisted-dev-session",
                outcome_detail="Previous development run.",
                created_at="2026-03-30T12:21:00Z",
                model="claude-sonnet-4-6",
            )
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_resumed(
                        repo_path,
                        config,
                        expected_session_id="persisted-dev-session",
                    ),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = resume_orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(runner.capture(1).session_id, "persisted-dev-session")
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

    def test_non_persistent_native_roles_ignore_persisted_sessions_after_fresh_orchestrator_invocation(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            task.status = "in_progress"
            task.workflow_current_step = "review"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "feature.txt", "implemented already\n")
            self.write_text(repo_path / "ready.txt", "ready\n")
            self.commit_all(repo_path, "feat: seed branch for review")
            self.git(repo_path, "checkout", "main")

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                session_id="persisted-dev-session",
                outcome_detail="Developer finished work.",
                created_at="2026-03-30T12:21:00Z",
                model="claude-sonnet-4-6",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                session_id="stale-review-session",
                outcome="deny",
                outcome_detail="Previous review session.",
                created_at="2026-03-30T12:22:00Z",
                model="claude-sonnet-4-6",
            )

            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_reviewer_approve(config),
                }
            )
            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = resume_orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertIsNone(runner.capture(1).session_id)
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

    def test_native_runner_infra_retries_are_persisted_and_block_the_task_on_exhaustion(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                task_title="Handle runner outage",
            )
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["max_infra_retries"] = 2
            store.save_project(project)
            runner = ScriptedNativeRunner(
                {
                    1: InfrastructureError("claude unavailable"),
                    2: InfrastructureError("claude unavailable"),
                    3: InfrastructureError("claude unavailable"),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
                runner_sleep=lambda _: None,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "blocked")
            blocked_task = store.get_task(task.id)
            self.assertIsNotNone(blocked_task)
            assert blocked_task is not None
            self.assertEqual(blocked_task.status, "blocked")
            self.assertEqual(
                blocked_task.blocked_reason,
                "claude unavailable",
            )

            event_types = [event.event_type for event in store.list_events(task_id=task.id)]
            self.assertEqual(event_types.count("agent.infra_error"), 2)
            self.assertIn("agent.error", event_types)
            runs = store.list_runs(task_id=task.id)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "failed")
            self.assertEqual(runs[0].outcome, "error")

    def test_native_runner_preflight_failure_is_not_retried(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                task_title="Handle missing Claude executable",
            )
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["max_infra_retries"] = 2
            store.save_project(project)
            runner = ScriptedNativeRunner(
                {
                    1: PreflightError(
                        "Claude Code preflight failed: executable `claude` was not found in PATH."
                    ),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
                runner_sleep=lambda _: None,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "blocked")
            self.assertEqual(runner.call_count, 1)
            blocked_task = store.get_task(task.id)
            self.assertIsNotNone(blocked_task)
            assert blocked_task is not None
            self.assertEqual(blocked_task.status, "blocked")
            self.assertEqual(
                blocked_task.blocked_reason,
                "Claude Code preflight failed: executable `claude` was not found in PATH.",
            )

            events = store.list_events(task_id=task.id)
            self.assertNotIn("agent.infra_error", [event.event_type for event in events])
            error_events = [event for event in events if event.event_type == "agent.error"]
            self.assertEqual(len(error_events), 1)
            self.assertTrue(error_events[0].payload["preflight_failed"])
            self.assertIn("executable `claude` was not found in PATH", error_events[0].payload["error"])
            runs = store.list_runs(task_id=task.id)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "failed")
            self.assertEqual(runs[0].outcome, "error")
            self.assertIn("preflight failed", runs[0].outcome_detail.lower())
            self.assertEqual(current_branch(repo_path), "main")

    def test_native_runner_uses_project_time_limit_for_timeout_seconds(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["time_limit_per_run_minutes"] = 7
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(repo_path, config),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(runner.capture(1).timeout_seconds, 420)
            self.assertEqual(runner.capture(2).timeout_seconds, 420)

    def test_run_project_waits_for_non_stale_active_run_before_starting_other_tasks(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            project.settings["time_limit_per_run_minutes"] = 10
            store.save_project(project)
            task.status = "in_progress"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            waiting_task = Task(
                id="task-2",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Second task",
                status="todo",
                created_at="2026-03-30T12:21:00Z",
            )
            store.save_task(waiting_task)
            active_run = Run(
                id="run-active",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(active_run)
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                utc_now=lambda: datetime(2026, 3, 30, 12, 25, 0, tzinfo=timezone.utc),
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, ())
            self.assertEqual(result.stop_reason, "waiting")
            refreshed_waiting_task = store.get_task(waiting_task.id)
            assert refreshed_waiting_task is not None
            self.assertEqual(refreshed_waiting_task.status, "todo")

    def test_project_run_task_rejects_non_stale_active_running_run(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["time_limit_per_run_minutes"] = 10
            store.save_project(project)
            task.status = "in_progress"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            active_run = Run(
                id="run-active",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(active_run)
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                utc_now=lambda: datetime(2026, 3, 30, 12, 25, 0, tzinfo=timezone.utc),
            )

            with self.assertRaises(OrchestratorError) as exc:
                orchestrator.run_project(project.id, task_id=task.id)

            self.assertIn("already has an active run", str(exc.exception))
            refreshed_task = store.get_task(task.id)
            assert refreshed_task is not None
            self.assertEqual(refreshed_task.status, "in_progress")
            refreshed_run = store.get_run(active_run.id)
            assert refreshed_run is not None
            self.assertEqual(refreshed_run.status, "running")

    def test_recover_orphaned_tasks_only_recovers_stale_running_runs(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["time_limit_per_run_minutes"] = 1
            store.save_project(project)
            task.status = "in_progress"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            fresh_task = Task(
                id="task-2",
                sprint_id=task.sprint_id,
                project_id=project.id,
                title="Fresh in-progress task",
                status="in_progress",
                branch_name="feat/task-2-fresh",
                started_at="2026-03-30T12:29:30Z",
                created_at="2026-03-30T12:29:00Z",
            )
            store.save_task(fresh_task)
            stale_run = Run(
                id="run-stale",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(stale_run)
            fresh_run = Run(
                id="run-fresh",
                task_id=fresh_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:29:30Z",
                created_at="2026-03-30T12:29:30Z",
            )
            store.save_run(fresh_run)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                utc_now=lambda: datetime(2026, 3, 30, 12, 30, 0, tzinfo=timezone.utc),
            )

            orchestrator.recover_orphaned_tasks(project.id)

            refreshed_task = store.get_task(task.id)
            assert refreshed_task is not None
            self.assertEqual(refreshed_task.status, "todo")
            self.assertEqual(refreshed_task.step_visit_counts, {})
            refreshed_run = store.get_run(stale_run.id)
            assert refreshed_run is not None
            self.assertEqual(refreshed_run.status, "failed")
            self.assertEqual(
                refreshed_run.outcome_detail,
                "Recovered stale running run after exceeding the active-run limit.",
            )
            refreshed_fresh_task = store.get_task(fresh_task.id)
            assert refreshed_fresh_task is not None
            self.assertEqual(refreshed_fresh_task.status, "in_progress")
            refreshed_fresh_run = store.get_run(fresh_run.id)
            assert refreshed_fresh_run is not None
            self.assertEqual(refreshed_fresh_run.status, "running")

    def test_run_project_prunes_old_done_task_events_and_preserves_blocked_history(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        fixed_now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)
        cutoff = (fixed_now - timedelta(days=7)).isoformat(timespec="microseconds").replace("+00:00", "Z")

        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            project.settings["event_retention_days"] = 7
            store.save_project(project)

            blocked_task = Task(
                id="task-blocked",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Blocked historical task",
                status="blocked",
                blocked_reason="Waiting on approval",
                created_at="2026-03-01T12:00:00Z",
            )
            previous_sprint = Sprint(
                id="sprint-0",
                project_id=project.id,
                title="Earlier sprint",
                status="completed",
                created_at="2026-03-01T10:00:00Z",
                completed_at="2026-03-10T10:00:00Z",
            )
            done_task = Task(
                id="task-done-old",
                sprint_id=previous_sprint.id,
                project_id=project.id,
                title="Old completed task",
                status="done",
                created_at="2026-03-01T12:05:00Z",
                completed_at="2026-03-02T12:05:00Z",
            )
            store.save_sprint(previous_sprint)
            store.save_task(blocked_task)
            store.save_task(done_task)

            blocked_run = Run(
                id="run-blocked-old",
                task_id=blocked_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="failed",
                created_at="2026-03-01T12:10:00Z",
            )
            done_run = Run(
                id="run-done-old",
                task_id=done_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="done",
                agent_backend="claude_code",
                status="completed",
                created_at="2026-03-01T12:12:00Z",
            )
            store.save_run(blocked_run)
            store.save_run(done_run)

            blocked_event = Event(
                id="event-blocked-old",
                run_id=blocked_run.id,
                task_id=blocked_task.id,
                project_id=project.id,
                event_type="signal.blocker",
                timestamp="2026-03-01T12:15:00.000000Z",
                payload={"message": "Keep me"},
            )
            old_done_event = Event(
                id="event-done-old",
                run_id=done_run.id,
                task_id=done_task.id,
                project_id=project.id,
                event_type="signal.completion",
                timestamp="2026-03-01T12:20:00.000000Z",
                payload={"summary": "Prune me"},
            )
            store.save_event(blocked_event)
            store.save_event(old_done_event)

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.write_text(repo_path / "feature.txt", "retention-safe implementation\n")
                self.write_text(repo_path / "ready.txt", "ready\n")
                self.commit_all(repo_path, "feat: finish pruning slice")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Finished the pruning slice.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Finished the pruning slice.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after review.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                    }
                ),
                utc_now=lambda: fixed_now,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "blocked")
            self.assertIsNotNone(store.get_event(blocked_event.id))
            self.assertIsNone(store.get_event(old_done_event.id))

            pruned_events = [
                event
                for event in store.list_events(project_id=project.id)
                if event.event_type == "engine.event_pruned"
            ]
            self.assertEqual(len(pruned_events), 1)
            self.assertEqual(
                pruned_events[0].payload,
                {
                    "count": 1,
                    "older_than": cutoff,
                },
            )

    def test_native_runner_executes_codex_roles_without_an_injected_executor(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "gpt-5.4"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            codex_roles = self.roles_with_backend(
                "codex",
                role_models={
                    "architect": "o3",
                    "code_reviewer": "gpt-5.4",
                    "developer": "",
                    "security_reviewer": "gpt-5.4",
                },
            )
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(repo_path, config),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=codex_roles,
                workflows=self.workflows,
                agent_runners={"codex": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "idle")
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(runner.capture(1).model, "gpt-5.4")
            self.assertEqual(
                runner.capture(2).disallowed_tools,
                ("Bash", "Write", "Edit", "NotebookEdit"),
            )

            runs = store.list_runs(task_id=task.id)
            self.assertEqual(
                [run.workflow_step for run in runs if run.role_id != "_builtin:orchestrator"],
                ["develop", "review", "test", "merge", "done"],
            )
            self.assertEqual(runs[0].agent_backend, "codex")
            self.assertEqual(runs[1].agent_backend, "codex")
            self.assertEqual(runs[0].session_id, "dev-session")

    def test_native_runner_reuses_persistent_codex_sessions_after_review_denial(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "gpt-5.4"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            codex_roles = self.roles_with_backend(
                "codex",
                role_models={
                    "architect": "o3",
                    "code_reviewer": "gpt-5.4",
                    "developer": "",
                    "security_reviewer": "gpt-5.4",
                },
            )
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_initial_pass(repo_path, config),
                    2: lambda config: self._native_reviewer_deny(config),
                    3: lambda config: self._native_developer_followup(repo_path, config),
                    4: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=codex_roles,
                workflows=self.workflows,
                agent_runners={"codex": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(runner.capture(1).session_id, None)
            self.assertEqual(runner.capture(3).session_id, "dev-session")
            self.assertIn("Please add the ready marker.", runner.capture(3).prompt)
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

    def test_native_runner_reuses_persisted_codex_session_after_fresh_orchestrator_invocation(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "gpt-5.4"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            task.status = "in_progress"
            task.workflow_current_step = "develop"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="codex",
                session_id="persisted-thread-123",
                outcome_detail="Previous codex run.",
                created_at="2026-03-30T12:21:00Z",
                model="gpt-5.4",
            )
            codex_roles = self.roles_with_backend(
                "codex",
                role_models={
                    "architect": "o3",
                    "code_reviewer": "gpt-5.4",
                    "developer": "",
                    "security_reviewer": "gpt-5.4",
                },
            )
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_resumed(
                        repo_path,
                        config,
                        expected_session_id="persisted-thread-123",
                    ),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=codex_roles,
                workflows=self.workflows,
                agent_runners={"codex": runner},
            )

            result = resume_orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(runner.capture(1).session_id, "persisted-thread-123")
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

    def test_native_runner_executes_codex_resume_after_human_gate_approval(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_with_architect",
            )
            project.settings["default_model"] = "gpt-5.4"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            blocked_task = Task(
                id=task.id,
                sprint_id=task.sprint_id,
                project_id=task.project_id,
                title=task.title,
                description=task.description,
                status="blocked",
                task_type=task.task_type,
                priority=task.priority,
                order_index=task.order_index,
                branch_name="feat/task-1-implement-orchestrator-loop",
                acceptance_criteria=task.acceptance_criteria,
                blocked_reason="Awaiting human approval",
                workflow_current_step="human_approval",
                created_at=task.created_at,
                started_at="2026-03-30T12:20:00Z",
            )
            store.save_task(blocked_task)
            codex_roles = self.roles_with_backend(
                "codex",
                role_models={
                    "architect": "o3",
                    "code_reviewer": "gpt-5.4",
                    "developer": "",
                    "security_reviewer": "gpt-5.4",
                },
            )
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(repo_path, config),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=codex_roles,
                workflows=self.workflows,
                agent_runners={"codex": runner},
            )

            resume_result = resume_orchestrator.resume_human_gate(task.id, outcome="approve")

            self.assertFalse(resume_result.deferred)
            self.assertEqual(resume_result.next_step, "develop")
            self.assertEqual(resume_result.task.status, "done")
            self.assertEqual(runner.capture(1).model, "gpt-5.4")
            runs = store.list_runs(task_id=task.id)
            self.assertEqual(
                [run.workflow_step for run in runs if run.role_id != "_builtin:orchestrator"],
                ["human_approval", "develop", "review", "test", "merge", "done"],
            )
            self.assertEqual(runs[1].agent_backend, "codex")

    def _native_developer_success(
        self,
        repo_path: Path,
        config: AgentRunConfig,
    ) -> tuple[AgentEvent, ...]:
        self.assertIn("## Task: Implement orchestrator loop", config.prompt)
        self.write_text(repo_path / "feature.txt", "implemented\n")
        self.write_text(repo_path / "ready.txt", "ready\n")
        self.commit_all(repo_path, "feat: implement workflow slice with native runner")
        return (
            AgentEvent(
                "agent.message",
                payload={"text": "Implemented the workflow slice.\nTASK_COMPLETE", "phase": "assistant"},
            ),
            AgentEvent(
                "agent.completed",
                payload={
                    "session_id": "dev-session",
                    "cost_usd": 1.2,
                    "duration_ms": 1200,
                    "token_count": 250,
                },
            ),
        )

    def _native_developer_initial_pass(
        self,
        repo_path: Path,
        config: AgentRunConfig,
    ) -> tuple[AgentEvent, ...]:
        self.assertIsNone(config.session_id)
        self.write_text(repo_path / "feature.txt", "initial implementation\n")
        self.commit_all(repo_path, "feat: initial native runner implementation")
        return (
            AgentEvent(
                "agent.message",
                payload={"text": "Initial implementation complete.\nTASK_COMPLETE", "phase": "assistant"},
            ),
            AgentEvent(
                "agent.completed",
                payload={
                    "session_id": "dev-session",
                    "cost_usd": 1.0,
                    "duration_ms": 900,
                    "token_count": 200,
                },
            ),
        )

    def _native_developer_followup(
        self,
        repo_path: Path,
        config: AgentRunConfig,
    ) -> tuple[AgentEvent, ...]:
        self.assertEqual(config.session_id, "dev-session")
        self.write_text(repo_path / "feature.txt", "updated after review\n")
        self.write_text(repo_path / "ready.txt", "ready\n")
        self.commit_all(repo_path, "fix: address review feedback with native runner")
        return (
            AgentEvent(
                "agent.message",
                payload={"text": "Updated after review feedback.\nTASK_COMPLETE", "phase": "assistant"},
            ),
            AgentEvent(
                "agent.completed",
                payload={
                    "session_id": "dev-session",
                    "cost_usd": 1.4,
                    "duration_ms": 1000,
                    "token_count": 230,
                },
            ),
        )

    def _native_developer_resumed(
        self,
        repo_path: Path,
        config: AgentRunConfig,
        *,
        expected_session_id: str,
    ) -> tuple[AgentEvent, ...]:
        self.assertEqual(config.session_id, expected_session_id)
        self.write_text(repo_path / "feature.txt", "resumed implementation\n")
        self.write_text(repo_path / "ready.txt", "ready\n")
        self.commit_all(repo_path, "fix: resume native runner session")
        return (
            AgentEvent(
                "agent.message",
                payload={"text": "Resumed existing session.\nTASK_COMPLETE", "phase": "assistant"},
            ),
            AgentEvent(
                "agent.completed",
                payload={
                    "session_id": expected_session_id,
                    "cost_usd": 1.1,
                    "duration_ms": 850,
                    "token_count": 180,
                },
            ),
        )

    def _native_reviewer_approve(self, config: AgentRunConfig) -> tuple[AgentEvent, ...]:
        self.assertIn("Use Read, Glob, and Grep", config.prompt)
        return (
            AgentEvent(
                "agent.message",
                payload={"text": "APPROVE", "phase": "result"},
            ),
            AgentEvent(
                "agent.completed",
                payload={"cost_usd": 0.2, "duration_ms": 200, "token_count": 40},
            ),
        )

    def _native_reviewer_deny(self, config: AgentRunConfig) -> tuple[AgentEvent, ...]:
        self.assertIn("Initial implementation complete.", config.prompt)
        return (
            AgentEvent(
                "agent.message",
                payload={"text": "DENY: Please add the ready marker.", "phase": "result"},
            ),
            AgentEvent(
                "agent.completed",
                payload={"cost_usd": 0.2, "duration_ms": 210, "token_count": 41},
            ),
        )

    def test_missing_transition_uses_workflow_fallback_and_blocks_the_task(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                task_title="Handle unknown review outcome",
            )

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.write_text(repo_path / "feature.txt", "implemented\n")
                self.commit_all(repo_path, "feat: implement fallback scenario")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the fallback scenario.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIn("Implemented the fallback scenario.", prompt)
                self.assertIsNone(carried_output)
                return AgentExecutionResult(
                    outcome="unknown",
                    detail="Outcome not mapped in the workflow.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                    }
                ),
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.blocked_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "blocked")

            blocked_task = store.get_task(task.id)
            self.assertIsNotNone(blocked_task)
            assert blocked_task is not None
            self.assertEqual(blocked_task.status, "blocked")
            self.assertEqual(
                blocked_task.blocked_reason,
                "Unhandled workflow outcome. Requires human review.",
            )

            events = store.list_events(task_id=task.id)
            no_transition = [
                event for event in events if event.event_type == "workflow.no_transition"
            ]
            self.assertEqual(len(no_transition), 1)
            self.assertEqual(
                no_transition[0].payload,
                {"step": "review", "outcome": "unknown"},
            )

    def test_sprint_cost_limit_blocks_task_before_next_step_runs(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                workflow_id="development",
                default_branch="main",
                settings={"cost_limit_per_sprint_usd": 5.0},
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Budgeted sprint",
                status="active",
                created_at="2026-03-30T12:05:00Z",
                started_at="2026-03-30T12:10:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Blocked by sprint budget",
                status="todo",
                created_at="2026-03-30T12:15:00Z",
            )
            prior_task = Task(
                id="task-prior",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Earlier expensive task",
                status="done",
                created_at="2026-03-30T12:14:00Z",
                completed_at="2026-03-30T12:14:30Z",
            )
            prior_run = Run(
                id="run-prior",
                task_id=prior_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="codex",
                status="completed",
                outcome="done",
                cost_usd=5.25,
                token_count=250,
                created_at="2026-03-30T12:14:00Z",
                started_at="2026-03-30T12:14:00Z",
                completed_at="2026-03-30T12:14:30Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(prior_task)
            store.save_task(task)
            store.save_run(prior_run)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.blocked_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "blocked")

            blocked_task = store.get_task(task.id)
            self.assertIsNotNone(blocked_task)
            assert blocked_task is not None
            self.assertEqual(blocked_task.status, "blocked")
            self.assertEqual(
                blocked_task.blocked_reason,
                "Sprint cost $5.25 exceeds limit $5.00",
            )

            runs = store.list_runs(task_id=task.id)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].role_id, "_builtin:orchestrator")
            self.assertEqual(runs[0].outcome, "blocked")

            cost_events = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "gate.cost_exceeded"
            ]
            self.assertEqual(len(cost_events), 1)
            self.assertEqual(
                cost_events[0].payload,
                {
                    "limit_usd": 5.0,
                    "actual_usd": 5.25,
                    "scope": "sprint",
                },
            )

    def test_select_next_task_skips_unsatisfied_dependencies(self) -> None:
        repo_path, db_path = self.create_workspace()
        repo_path.mkdir(exist_ok=True)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                workflow_id="development",
                default_branch="main",
                settings={"task_selection_mode": "directed"},
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Orchestrator",
                status="active",
                created_at="2026-03-30T12:05:00Z",
                started_at="2026-03-30T12:10:00Z",
            )
            blocked_task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Blocked by dependency",
                status="todo",
                priority=0,
                depends_on_task_ids=["task-missing"],
                created_at="2026-03-30T12:15:00Z",
            )
            ready_task = Task(
                id="task-2",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Ready task",
                status="todo",
                priority=1,
                created_at="2026-03-30T12:16:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(blocked_task)
            store.save_task(ready_task)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
            )

            selected = orchestrator.select_next_task(project)

            self.assertIsNotNone(selected)
            assert selected is not None
            self.assertEqual(selected.id, ready_task.id)

    def test_run_project_writes_runtime_context_before_agent_runs_and_after_task_completion(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del carried_output
                context_path = repo_path / ".foreman" / "context.md"
                status_path = repo_path / ".foreman" / "status.md"
                self.assertTrue(context_path.is_file())
                self.assertTrue(status_path.is_file())
                self.assertIn("Sprint: Orchestrator", context_path.read_text(encoding="utf-8"))
                self.assertIn(
                    "* [in_progress] Implement orchestrator loop (task-1)",
                    context_path.read_text(encoding="utf-8"),
                )
                self.assertIn("## Current Sprint Detail", status_path.read_text(encoding="utf-8"))
                self.assertIn("Title: Orchestrator", status_path.read_text(encoding="utf-8"))
                self.assertIn("# Sprint Context", prompt)
                self.write_text(repo_path / "feature.txt", "implemented\n")
                self.write_text(repo_path / "ready.txt", "ready\n")
                self.commit_all(repo_path, "feat: implement workflow slice")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the workflow slice.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Implemented the workflow slice.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after review.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                    }
                ),
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            context_text = (repo_path / ".foreman" / "context.md").read_text(encoding="utf-8")
            status_text = (repo_path / ".foreman" / "status.md").read_text(encoding="utf-8")
            self.assertIn("* [done] Implement orchestrator loop (task-1)", context_text)
            self.assertIn("Status: done", context_text)
            self.assertIn(
                "Task counts: todo=0 in_progress=0 blocked=0 done=1 cancelled=0",
                status_text,
            )

            context_events = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "engine.context_write"
            ]
            self.assertGreaterEqual(len(context_events), 4)
            self.assertIn(
                {"path": ".foreman/context.md"},
                [event.payload for event in context_events],
            )
            self.assertIn(
                {"path": ".foreman/status.md"},
                [event.payload for event in context_events],
            )

    def test_builtin_context_write_reuses_runtime_projection(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            workflow = WorkflowDefinition(
                id="development_with_context_write",
                name="Development With Context Write",
                methodology="development",
                steps=(
                    WorkflowStep(id="develop", role="developer"),
                    WorkflowStep(id="sync_context", role="_builtin:context_write"),
                    WorkflowStep(id="done", role="_builtin:mark_done"),
                ),
                transitions=(
                    WorkflowTransition(
                        from_step="develop",
                        trigger="completion:done",
                        to_step="sync_context",
                    ),
                    WorkflowTransition(
                        from_step="sync_context",
                        trigger="completion:success",
                        to_step="done",
                    ),
                ),
                gates=(),
                fallback=WorkflowFallback(
                    action="block",
                    message="Unhandled workflow outcome.",
                ),
                source_path=Path("tests"),
            )

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                del carried_output
                self.assertIn("# Sprint Context", prompt)
                self.write_text(repo_path / "feature.txt", "implemented\n")
                self.commit_all(repo_path, "feat: implement context-write workflow")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the workflow slice.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows={workflow.id: workflow},
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                    }
                ),
            )

            project.workflow_id = workflow.id
            store.save_project(project)
            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertTrue((repo_path / ".foreman" / "context.md").is_file())
            self.assertTrue((repo_path / ".foreman" / "status.md").is_file())

            runs = store.list_runs(task_id=task.id)
            workflow_runs = [r for r in runs if r.role_id != "_builtin:orchestrator"]
            self.assertEqual(
                [run.workflow_step for run in workflow_runs],
                ["develop", "sync_context", "done"],
            )
            context_events = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "engine.context_write"
            ]
            sync_context_run = next(run for run in runs if run.workflow_step == "sync_context")
            sync_context_payloads = [
                event.payload for event in context_events if event.run_id == sync_context_run.id
            ]
            self.assertEqual(
                sync_context_payloads,
                [
                    {"path": ".foreman/context.md"},
                    {"path": ".foreman/status.md"},
                ],
            )


class AutonomousTaskSelectionTests(unittest.TestCase):
    """Tests for select_next_task in autonomous mode."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.roles = load_roles(default_roles_dir())
        cls.workflows = load_workflows(
            default_workflows_dir(),
            available_role_ids=set(cls.roles),
        )

    def _make_store(self) -> tuple[ForemanStore, str]:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        db_path = str(Path(self._tmp.name) / "foreman.db")
        store = ForemanStore(db_path)
        store.initialize()
        return store, db_path

    def _seed(
        self,
        store: ForemanStore,
        *,
        selection_mode: str = "autonomous",
        max_autonomous_tasks: int | None = None,
    ) -> tuple[Project, "Sprint"]:
        settings: dict = {"task_selection_mode": selection_mode}
        if max_autonomous_tasks is not None:
            settings["max_autonomous_tasks"] = max_autonomous_tasks
        project = Project(
            id="proj-auto",
            name="Auto Project",
            repo_path="/tmp/auto",
            workflow_id="development",
            settings=settings,
        )
        sprint = Sprint(
            id="sprint-auto",
            project_id=project.id,
            title="Auto Sprint",
            status="active",
        )
        store.save_project(project)
        store.save_sprint(sprint)
        return project, sprint

    def _orchestrator(self, store: ForemanStore) -> ForemanOrchestrator:
        return ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

    def test_autonomous_no_sprint_returns_none(self) -> None:
        store, _ = self._make_store()
        project = Project(
            id="proj-nosprint",
            name="No Sprint",
            repo_path="/tmp/nosprint",
            workflow_id="development",
            settings={"task_selection_mode": "autonomous"},
        )
        store.save_project(project)
        orc = self._orchestrator(store)
        result = orc.select_next_task(project)
        self.assertIsNone(result)

    def test_autonomous_creates_placeholder_task(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store)
        orc = self._orchestrator(store)

        selected = orc.select_next_task(project)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.sprint_id, sprint.id)
        self.assertEqual(selected.project_id, project.id)
        self.assertEqual(selected.created_by, "orchestrator")
        self.assertEqual(selected.title, "[autonomous] new task")
        # Task should be persisted.
        persisted = store.get_task(selected.id)
        self.assertIsNotNone(persisted)

    def test_autonomous_resumes_inprogress_before_creating(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store)
        existing = Task(
            id="task-existing",
            sprint_id=sprint.id,
            project_id=project.id,
            title="In-flight task",
            status="in_progress",
            workflow_current_step="develop",
            created_by="orchestrator",
        )
        store.save_task(existing)
        orc = self._orchestrator(store)

        selected = orc.select_next_task(project)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.id, existing.id)
        # No new placeholder should have been created.
        all_tasks = store.list_tasks(sprint_id=sprint.id)
        self.assertEqual(len(all_tasks), 1)

    def test_autonomous_waits_for_live_in_progress_task_before_creating_placeholder(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store)
        existing = Task(
            id="task-existing",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Live native task",
            status="in_progress",
            created_by="orchestrator",
        )
        store.save_task(existing)
        orc = self._orchestrator(store)

        selected = orc.select_next_task(project)

        self.assertIsNone(selected)
        all_tasks = store.list_tasks(sprint_id=sprint.id)
        self.assertEqual(len(all_tasks), 1)

    def test_autonomous_respects_max_autonomous_tasks_limit(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store, max_autonomous_tasks=2)
        for i in range(2):
            store.save_task(Task(
                id=f"task-orc-{i}",
                sprint_id=sprint.id,
                project_id=project.id,
                title=f"Orchestrator task {i}",
                status="done",
                created_by="orchestrator",
            ))
        orc = self._orchestrator(store)

        result = orc.select_next_task(project)

        self.assertIsNone(result)

    def test_autonomous_default_limit_is_five(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store)  # no max_autonomous_tasks override
        for i in range(5):
            store.save_task(Task(
                id=f"task-orc-{i}",
                sprint_id=sprint.id,
                project_id=project.id,
                title=f"Orchestrator task {i}",
                status="done",
                created_by="orchestrator",
            ))
        orc = self._orchestrator(store)

        result = orc.select_next_task(project)

        self.assertIsNone(result)

    def test_autonomous_human_created_tasks_dont_count_toward_limit(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store, max_autonomous_tasks=1)
        # Five human-created tasks — should not count against the autonomous limit.
        for i in range(5):
            store.save_task(Task(
                id=f"task-human-{i}",
                sprint_id=sprint.id,
                project_id=project.id,
                title=f"Human task {i}",
                status="todo",
                created_by="human",
            ))
        orc = self._orchestrator(store)

        selected = orc.select_next_task(project)

        # One placeholder should be created because no orchestrator task exists yet.
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.created_by, "orchestrator")

    def test_directed_mode_unchanged(self) -> None:
        store, _ = self._make_store()
        project = Project(
            id="proj-directed",
            name="Directed",
            repo_path="/tmp/directed",
            workflow_id="development",
            settings={"task_selection_mode": "directed"},
        )
        sprint = Sprint(
            id="sprint-directed",
            project_id=project.id,
            title="Sprint",
            status="active",
        )
        task = Task(
            id="task-d",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Directed task",
            status="todo",
        )
        store.save_project(project)
        store.save_sprint(sprint)
        store.save_task(task)
        orc = self._orchestrator(store)

        selected = orc.select_next_task(project)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.id, task.id)

    def test_unknown_selection_mode_raises(self) -> None:
        store, _ = self._make_store()
        project = Project(
            id="proj-unknown",
            name="Unknown Mode",
            repo_path="/tmp/unknown",
            workflow_id="development",
            settings={"task_selection_mode": "galactic"},
        )
        store.save_project(project)
        orc = self._orchestrator(store)

        with self.assertRaises(OrchestratorError):
            orc.select_next_task(project)


if __name__ == "__main__":
    unittest.main()


class DecisionExtractionTests(unittest.TestCase):
    """Unit coverage for reviewer decision parsing."""

    def test_extract_decision_output_accepts_preamble_and_markdown_wrapped_verdict(self) -> None:
        outcome, detail = _extract_decision_output(
            "I verified the changes.\n\nEverything checks out.\n\n**APPROVE**"
        )

        self.assertEqual(outcome, "approve")
        self.assertEqual(detail, "APPROVE")

    def test_extract_decision_output_accepts_trailing_deny_reason(self) -> None:
        outcome, detail = _extract_decision_output(
            "I found one issue.\n\n- DENY: add the missing migration test"
        )

        self.assertEqual(outcome, "deny")
        self.assertEqual(detail, "add the missing migration test")


class CompletionEvidenceTests(unittest.TestCase):
    """Regression coverage for CompletionEvidence false-positive scenarios.

    Proves that Foreman does not treat docs-only or tests-only changes as
    sufficient completion for implementation-oriented backend tasks when the
    completion evidence does not support that outcome.

    False-positive scenarios covered:
    - docs-only:    no implementation code changed (verdict = insufficient)
    - tests-only:  tests added but no implementation code (verdict <= weak)
    - approval-only: reviewer approval without evidence of actual implementation
    - text-only:    agent output text without matching code changes (weak verdict)
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.roles = load_roles(default_roles_dir())
        cls.workflows = load_workflows(
            default_workflows_dir(),
            available_role_ids=set(cls.roles),
        )

    def create_workspace(self) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo_path = root / "repo"
        repo_path.mkdir()
        db_path = root / "foreman.db"
        return repo_path, db_path

    def git(self, repo_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)} failed in {repo_path}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit_all(self, repo_path: Path, message: str) -> None:
        self.git(repo_path, "add", ".")
        self.git(repo_path, "commit", "-m", message)

    def initialize_repo(self, repo_path: Path) -> None:
        self.git(repo_path, "init")
        self.git(repo_path, "checkout", "-b", "main")
        self.git(repo_path, "config", "user.email", "foreman-tests@example.com")
        self.git(repo_path, "config", "user.name", "Foreman Tests")
        self.write_text(repo_path / "AGENTS.md", "# Local Instructions\nUse tests.\n")
        self.write_text(repo_path / ".gitignore", ".foreman/\n")
        self.write_text(repo_path / "README.md", "# Temp Repo\n")
        self.commit_all(repo_path, "chore: initial commit")

    def seed_project(
        self,
        store: ForemanStore,
        *,
        repo_path: Path,
        acceptance_criteria: str | None = None,
        branch_name: str | None = "feat/task-fp-1",
    ) -> tuple[Project, Sprint, Task]:
        project = Project(
            id="project-fp",
            name="False-Positive Test",
            repo_path=str(repo_path),
            spec_path="docs/specs/engine-design-v3.md",
            workflow_id="development",
            default_branch="main",
            settings={
                "task_selection_mode": "directed",
                "test_command": "test -f ready.txt",
                "default_model": "gpt-5.4",
            },
            created_at="2026-04-22T10:00:00Z",
            updated_at="2026-04-22T10:00:00Z",
        )
        sprint = Sprint(
            id="sprint-fp",
            project_id=project.id,
            title="False-Positive Sprint",
            goal="Validate completion truth",
            status="active",
            order_index=1,
            created_at="2026-04-22T10:05:00Z",
            started_at="2026-04-22T10:10:00Z",
        )
        task = Task(
            id="task-fp-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Implement the scheduler queue",
            description="Build a persistent task scheduler.",
            status="todo",
            task_type="feature",
            priority=1,
            order_index=1,
            acceptance_criteria=acceptance_criteria,
            branch_name=branch_name,
            created_at="2026-04-22T10:15:00Z",
        )
        store.save_project(project)
        store.save_sprint(sprint)
        store.save_task(task)
        return project, sprint, task

    def seed_run(
        self,
        store: ForemanStore,
        *,
        project: Project,
        task: Task,
        role_id: str,
        workflow_step: str,
        agent_backend: str,
        created_at: str,
        outcome: str = "done",
        outcome_detail: str = "Completed.",
        status: str = "completed",
    ) -> Run:
        run = Run(
            id=f"run-fp-{len(store.list_runs(task_id=task.id)) + 1}",
            task_id=task.id,
            project_id=project.id,
            role_id=role_id,
            workflow_step=workflow_step,
            agent_backend=agent_backend,
            status=status,
            outcome=outcome,
            outcome_detail=outcome_detail,
            created_at=created_at,
        )
        store.save_run(run)
        return run

    def seed_test_events(
        self,
        store: ForemanStore,
        run: Run,
        task: Task,
        project: Project,
        passed: bool,
        timestamp: str,
        command: str = "pytest tests/",
    ) -> None:
        test_run_event = Event(
            id=f"event-test-run-{task.id}-{run.id}",
            run_id=run.id,
            task_id=task.id,
            project_id=project.id,
            event_type="engine.test_run",
            timestamp=timestamp,
            payload={"command": command, "passed": passed},
        )
        test_output_event = Event(
            id=f"event-test-output-{task.id}-{run.id}",
            run_id=run.id,
            task_id=task.id,
            project_id=project.id,
            event_type="engine.test_output",
            timestamp=timestamp,
            payload={"exit_code": 0 if passed else 1, "output": "ok" if passed else "FAILED"},
        )
        store.save_event(test_run_event)
        store.save_event(test_output_event)

    def test_build_completion_evidence_returns_correct_structure(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the orchestrator.\nWrite tests for it.",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the orchestrator module with proper structure.",
                created_at="2026-04-22T10:20:00Z",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                outcome="approve",
                outcome_detail="Implementation looks correct.",
                created_at="2026-04-22T10:25:00Z",
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "orchestrator.py", "def run(): pass\n")
            self.commit_all(repo_path, "feat: implement orchestrator")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            self.assertEqual(evidence.task_id, task.id)
            self.assertEqual(evidence.task_title, task.title)
            self.assertEqual(evidence.acceptance_criteria, task.acceptance_criteria)
            self.assertEqual(evidence.criteria_count, 2)
            self.assertGreater(len(evidence.agent_outputs), 0)
            self.assertIn("orchestrator.py", evidence.changed_files)
            self.assertIn("1 file", evidence.branch_diff_stat)

    def test_build_completion_evidence_scores_passed_tests_higher(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement feature.\nAdd tests.",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the feature module with comprehensive tests.",
                created_at="2026-04-22T10:20:00Z",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                outcome="approve",
                outcome_detail="Code review passed.",
                created_at="2026-04-22T10:25:00Z",
            )
            test_run = self.seed_run(
                store,
                project=project,
                task=task,
                role_id="_builtin:test",
                workflow_step="test",
                agent_backend="builtin",
                outcome="success",
                outcome_detail="All tests passed.",
                created_at="2026-04-22T10:30:00Z",
            )
            self.seed_test_events(
                store, test_run, task, project, passed=True, timestamp="2026-04-22T10:30:00Z"
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "feature.py", "def feature(): return True\n")
            self.commit_all(repo_path, "feat: add feature")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            self.assertTrue(evidence.builtin_test_passed)
            self.assertEqual(evidence.builtin_test_result, "pytest tests/")
            self.assertGreater(evidence.score, 0)
            self.assertIn("test=30", evidence.score_breakdown)

    def test_build_completion_evidence_failing_test_receives_zero_test_points(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement feature.\nAdd tests.",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the feature module.",
                created_at="2026-04-22T10:20:00Z",
            )
            test_run = self.seed_run(
                store,
                project=project,
                task=task,
                role_id="_builtin:test",
                workflow_step="test",
                agent_backend="builtin",
                outcome="failure",
                outcome_detail="Tests failed.",
                created_at="2026-04-22T10:25:00Z",
            )
            self.seed_test_events(
                store, test_run, task, project, passed=False, timestamp="2026-04-22T10:25:00Z"
            )

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            self.assertFalse(evidence.builtin_test_passed)
            self.assertIn("test=0", evidence.score_breakdown)

    def test_build_completion_evidence_verdict_weak_when_no_criteria_addressed(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd priority handling.\n",
            )

            # Empty output — nothing addresses the criteria
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Done.",
                created_at="2026-04-22T10:20:00Z",
            )

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            self.assertEqual(evidence.criteria_addressed, 0)
            self.assertLess(evidence.score, 40)
            self.assertIn(evidence.verdict, ("weak", "insufficient"))

    def test_build_completion_evidence_weak_verdict_despite_criteria_coverage_when_no_code_changes(
        self,
    ) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd priority handling.\n",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the scheduler queue with priority handling for tasks.",
                created_at="2026-04-22T10:20:00Z",
            )

            # No code changes made — only output text with no diff
            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            self.assertGreater(evidence.criteria_addressed, 0)
            self.assertGreaterEqual(evidence.score, 40)
            # Without code changes and no test result, verdict stays "weak" despite criteria coverage
            self.assertEqual(evidence.verdict, "weak")

    def test_build_completion_evidence_no_acceptance_criteria_handled_gracefully(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path, acceptance_criteria=None)

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Done.",
                created_at="2026-04-22T10:20:00Z",
            )

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            self.assertEqual(evidence.criteria_count, 0)
            self.assertEqual(evidence.verdict, "insufficient")
            self.assertIn("No acceptance criteria defined", evidence.verdict_reasons)

    # ------------------------------------------------------------------
    # False-positive regression tests: core acceptance criteria
    # ------------------------------------------------------------------

    def test_docs_only_changes_verdict_is_insufficient(self) -> None:
        """Docs-only changes with reviewer approval are NOT sufficient for implementation tasks.

        Even when a reviewer approves and the agent reports done, docs-only
        changes to a task about implementing backend code produce verdict=insufficient.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd priority handling.\nWrite integration tests.\n",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Documented the scheduler design in docs/scheduler.md",
                created_at="2026-04-22T10:20:00Z",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                outcome="approve",
                outcome_detail="Documentation looks great.",
                created_at="2026-04-22T10:25:00Z",
            )

            # Only docs changed — no implementation code
            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "docs" / "scheduler.md", "# Scheduler Design\n## Queue\n")
            self.commit_all(repo_path, "docs: document scheduler design")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            # Changed files are docs only — no .py implementation files
            self.assertTrue(
                all(
                    f.endswith(".md") or f.startswith("docs/")
                    for f in evidence.changed_files
                ),
                f"Expected docs-only changes, got: {evidence.changed_files}",
            )
            # Score is low: no criteria addressed, no code changes
            self.assertLess(evidence.score, 40)
            # Verdict must be insufficient — docs-only is not adequate for implementation task
            self.assertEqual(
                evidence.verdict,
                "insufficient",
                f"Expected verdict=insufficient for docs-only, got verdict={evidence.verdict!r} "
                f"(score={evidence.score}, breakdown={evidence.score_breakdown})",
            )

    def test_tests_only_changes_verdict_is_weak(self) -> None:
        """Tests-only changes with reviewer approval are NOT sufficient for implementation tasks.

        Adding tests for functionality that does not exist does not constitute
        implementation evidence — verdict stays weak or below adequate.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd priority handling.\n",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Added tests for the scheduler queue.",
                created_at="2026-04-22T10:20:00Z",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                outcome="approve",
                outcome_detail="Tests look reasonable.",
                created_at="2026-04-22T10:25:00Z",
            )

            # Only test file changed — no implementation code
            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "tests" / "test_scheduler.py", "def test_scheduler():\n    pass\n")
            self.commit_all(repo_path, "test: add scheduler tests")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            # Only test file changed
            self.assertTrue(
                any("test_scheduler" in f for f in evidence.changed_files),
                f"Expected test file in changed files, got: {evidence.changed_files}",
            )
            # No criteria addressed (no implementation for "scheduler" or "priority" in code)
            self.assertEqual(evidence.criteria_addressed, 0)
            # Score capped by file points alone
            self.assertLess(evidence.score, 60)
            # Verdict is weak or insufficient — tests-only is not adequate
            self.assertIn(
                evidence.verdict,
                ("weak", "insufficient"),
                f"Expected verdict in (weak, insufficient) for tests-only, got {evidence.verdict!r} "
                f"(score={evidence.score})",
            )

    def test_approval_without_implementation_is_insufficient(self) -> None:
        """Reviewer approval alone is not sufficient evidence for task completion.

        Even with APPROVE outcome and no other signals, the evidence verdict
        must reflect the absence of implementation work.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd priority handling.\n",
            )

            # Agent marks done but no detail about actual work
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Done.",
                created_at="2026-04-22T10:20:00Z",
            )
            # Reviewer approves with no substance
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                outcome="approve",
                outcome_detail="Looks fine.",
                created_at="2026-04-22T10:25:00Z",
            )

            # No branch or code changes
            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            # No criteria addressed
            self.assertEqual(evidence.criteria_addressed, 0)
            self.assertEqual(evidence.verdict, "insufficient")
            self.assertLess(evidence.score, 40)

    def test_text_claims_implementation_but_no_code_changes_produces_weak_verdict(self) -> None:
        """Agent output that claims implementation but has no matching code changes.

        The evidence model must detect this mismatch: text coverage alone does not
        overcome the absence of code changes for implementation-oriented tasks.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd priority handling.\n",
            )

            # Agent text claims it implemented the scheduler
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail=(
                    "Implemented the scheduler queue with priority handling. "
                    "The scheduler module now supports queue operations and priority-based ordering."
                ),
                created_at="2026-04-22T10:20:00Z",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                outcome="approve",
                outcome_detail="Implementation reviewed.",
                created_at="2026-04-22T10:25:00Z",
            )

            # No code changes on the branch
            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            # Criteria are partially addressed via text (scheduler/priority in output)
            # but verdict is weak because there are no code changes
            self.assertLessEqual(evidence.verdict, "weak")
            self.assertLess(evidence.score, 60)
            # The score breakdown should reflect low file-change points
            # (at most files=5 for no actual code changes)
            self.assertIn("files=", evidence.score_breakdown)

    def test_passed_tests_alone_without_implementation_is_weak_not_adequate(self) -> None:
        """Passing tests without any implementation code is insufficient evidence.

        A passing test run alone cannot support a verdict of adequate or higher
        when no implementation files changed.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd priority handling.\n",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Work complete.",
                created_at="2026-04-22T10:20:00Z",
            )
            test_run = self.seed_run(
                store,
                project=project,
                task=task,
                role_id="_builtin:test",
                workflow_step="test",
                agent_backend="builtin",
                outcome="success",
                outcome_detail="All tests passed.",
                created_at="2026-04-22T10:25:00Z",
            )
            self.seed_test_events(
                store, test_run, task, project, passed=True, timestamp="2026-04-22T10:25:00Z"
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            # Only a placeholder file — not a real implementation
            self.write_text(repo_path / "scheduler.py", "# TODO\n")
            self.commit_all(repo_path, "chore: placeholder")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            # Tests passed: 30 points from test component
            self.assertIn("test=30", evidence.score_breakdown)
            # But no real implementation: criteria_addressed stays 0
            self.assertEqual(evidence.criteria_addressed, 0)
            # Score maxes out at ~35 (30 test + 5 file) — still not adequate
            self.assertLess(evidence.score, 60)
            # Verdict is weak or insufficient — not adequate
            self.assertIn(
                evidence.verdict,
                ("weak", "insufficient"),
                f"Expected verdict in (weak, insufficient) for placeholder-only, "
                f"got {evidence.verdict!r} (score={evidence.score})",
            )

    def test_strong_verdict_requires_code_changes_plus_criteria_plus_passed_tests(self) -> None:
        """A 'strong' verdict requires all three: real code changes, addressed criteria, passing tests.

        This is the positive case — proving the model rewards genuine completion.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd priority handling.\n",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail=(
                    "Implemented the scheduler queue with priority handling. "
                    "scheduler.py and scheduler_test.py now cover queue operations."
                ),
                created_at="2026-04-22T10:20:00Z",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                outcome="approve",
                outcome_detail="Implementation is solid.",
                created_at="2026-04-22T10:25:00Z",
            )
            test_run = self.seed_run(
                store,
                project=project,
                task=task,
                role_id="_builtin:test",
                workflow_step="test",
                agent_backend="builtin",
                outcome="success",
                outcome_detail="All tests passed.",
                created_at="2026-04-22T10:30:00Z",
            )
            self.seed_test_events(
                store, test_run, task, project, passed=True, timestamp="2026-04-22T10:30:00Z"
            )

            # Real implementation files
            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(
                repo_path / "scheduler.py",
                "# Scheduler queue with priority handling\ndef enqueue(item): pass\n",
            )
            self.write_text(
                repo_path / "scheduler_test.py",
                "def test_scheduler(): pass\n",
            )
            self.commit_all(repo_path, "feat: implement scheduler with priority")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            # All three signals present
            self.assertGreater(evidence.criteria_addressed, 0)
            self.assertTrue(evidence.builtin_test_passed)
            self.assertGreater(len(evidence.changed_files), 0)
            self.assertTrue(
                any(f.endswith(".py") for f in evidence.changed_files),
                f"Expected Python implementation files, got: {evidence.changed_files}",
            )
            # Score must be adequate or above
            self.assertGreaterEqual(evidence.score, 60)
            self.assertIn(
                evidence.verdict,
                ("adequate", "strong"),
                f"Expected verdict in (adequate, strong) for strong completion, "
                f"got {evidence.verdict!r} (score={evidence.score})",
            )

    def test_no_branch_means_no_changed_files_evidence(self) -> None:
        """Tasks with no branch name have no diff evidence and rely solely on agent output.

        This guards against false positives from incomplete task metadata.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd priority handling.\n",
                branch_name=None,  # No branch set
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the scheduler.",
                created_at="2026-04-22T10:20:00Z",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                outcome="approve",
                outcome_detail="Approved.",
                created_at="2026-04-22T10:25:00Z",
            )

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            # No diff available when no branch
            self.assertEqual(evidence.changed_files, ())
            self.assertEqual(evidence.branch_diff_stat, "")
            # Verdict driven by output text alone — stays weak without code changes
            self.assertIn(
                evidence.verdict,
                ("weak", "insufficient"),
                f"Expected verdict in (weak, insufficient) for no-branch case, "
                f"got {evidence.verdict!r}",
            )

    def test_failing_test_cancels_test_score_points(self) -> None:
        """A failing built-in test must reduce the score to zero on the test component.

        This prevents test passes from masking incomplete implementation.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd tests.\n",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the scheduler module.",
                created_at="2026-04-22T10:20:00Z",
            )
            test_run = self.seed_run(
                store,
                project=project,
                task=task,
                role_id="_builtin:test",
                workflow_step="test",
                agent_backend="builtin",
                outcome="failure",
                outcome_detail="Tests failed.",
                created_at="2026-04-22T10:25:00Z",
            )
            self.seed_test_events(
                store, test_run, task, project, passed=False, timestamp="2026-04-22T10:25:00Z"
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "scheduler.py", "def scheduler(): pass\n")
            self.commit_all(repo_path, "feat: scheduler implementation")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            # Failing test: 0 points on test component
            self.assertFalse(evidence.builtin_test_passed)
            self.assertIn("test=0", evidence.score_breakdown)
            # Score is at most ~25 (criteria + files) — insufficient without test points
            self.assertLess(evidence.score, 60)
            self.assertEqual(evidence.verdict, "insufficient")


class CompletionGuardTests(unittest.TestCase):
    """Regression coverage for the _builtin:mark_done completion guard.

    Verifies that tasks with strong/adequate completion evidence are marked
    done, while tasks with weak/insufficient evidence are blocked and their
    blocked_reason is set to explain the weak verdict.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.roles = load_roles(default_roles_dir())
        cls.workflows = load_workflows(
            default_workflows_dir(),
            available_role_ids=set(cls.roles),
        )

    def create_workspace(self) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo_path = root / "repo"
        repo_path.mkdir()
        db_path = root / "foreman.db"
        return repo_path, db_path

    def git(self, repo_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)} failed in {repo_path}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit_all(self, repo_path: Path, message: str) -> None:
        self.git(repo_path, "add", ".")
        self.git(repo_path, "commit", "-m", message)

    def initialize_repo(self, repo_path: Path) -> None:
        self.git(repo_path, "init")
        self.git(repo_path, "checkout", "-b", "main")
        self.git(repo_path, "config", "user.email", "foreman-tests@example.com")
        self.git(repo_path, "config", "user.name", "Foreman Tests")
        self.write_text(repo_path / "AGENTS.md", "# Local Instructions\nUse tests.\n")
        self.write_text(repo_path / ".gitignore", ".foreman/\n")
        self.write_text(repo_path / "README.md", "# Temp Repo\n")
        self.commit_all(repo_path, "chore: initial commit")

    def seed_project(
        self,
        store: ForemanStore,
        *,
        repo_path: Path,
        acceptance_criteria: str,
    ) -> tuple[Project, Sprint, Task]:
        project = Project(
            id="proj-guard",
            name="Guard Test",
            repo_path=str(repo_path),
            spec_path="docs/specs/engine-design-v3.md",
            workflow_id="development",
            default_branch="main",
            settings={
                "task_selection_mode": "directed",
                "test_command": "test -f ready.txt",
            },
            created_at="2026-04-22T10:00:00Z",
            updated_at="2026-04-22T10:00:00Z",
        )
        sprint = Sprint(
            id="sprint-guard",
            project_id=project.id,
            title="Guard Sprint",
            status="active",
            order_index=1,
            created_at="2026-04-22T10:05:00Z",
            started_at="2026-04-22T10:10:00Z",
        )
        task = Task(
            id="task-guard-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Implement auth tokens",
            description="Build a token-based auth system.",
            status="todo",
            task_type="feature",
            priority=1,
            order_index=1,
            acceptance_criteria=acceptance_criteria,
            branch_name="feat/guard-test",
            created_at="2026-04-22T10:15:00Z",
        )
        store.save_project(project)
        store.save_sprint(sprint)
        store.save_task(task)
        return project, sprint, task

    def test_strong_verdict_allows_done(self) -> None:
        """A task with implementation changes is allowed through merge."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()

        project, sprint, task = self.seed_project(
            store,
            repo_path=repo_path,
            acceptance_criteria="Add JWT token generation\nAdd token validation middleware",
        )

        # Commit real implementation files and pass tests.
        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.write_text(
            repo_path / "auth.py",
            "import jwt\ndef generate_token(user_id): return jwt.encode({'uid': user_id}, 'secret')\n"
            "def validate_token(token): return jwt.decode(token, 'secret', algorithms=['HS256'])\n",
        )
        self.write_text(
            repo_path / "middleware.py",
            "def auth_middleware(request): return request.get('token') is not None\n",
        )
        self.write_text(repo_path / "tests/test_auth.py", "def test_token(): assert True\n")
        self.write_text(repo_path / "ready.txt", "ok\n")
        self.commit_all(repo_path, "feat: auth token implementation")
        self.git(repo_path, "checkout", "main")

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:merge",
            project=project,
            task=task,
            step_id="merge",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "success")
        self.assertNotEqual(task.status, "blocked")

    def test_insufficient_verdict_blocks_task(self) -> None:
        """A task with no material implementation changes is blocked before merge."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()

        project, sprint, task = self.seed_project(
            store,
            repo_path=repo_path,
            acceptance_criteria="Add JWT token generation\nAdd token validation middleware",
        )

        # No code changes — only a commit on the branch with no implementation.
        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.write_text(repo_path / "NOTES.md", "Will implement JWT auth next sprint.\n")
        self.commit_all(repo_path, "docs: outline auth approach")
        self.git(repo_path, "checkout", "main")

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:merge",
            project=project,
            task=task,
            step_id="merge",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "blocked")
        self.assertEqual(task.status, "blocked")
        self.assertIn("Completion evidence too weak", task.blocked_reason)
        self.assertIn("verdict:", task.blocked_reason)

    def test_weak_verdict_blocks_task(self) -> None:
        """A docs-only implementation branch is blocked before merge."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()

        project, sprint, task = self.seed_project(
            store,
            repo_path=repo_path,
            acceptance_criteria="Add scheduler queue",
        )

        # Only a docs file — no implementation.
        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.write_text(repo_path / "SCHEDULER.md", "# Scheduler Queue\nWill implement soon.\n")
        self.commit_all(repo_path, "docs: scheduler design doc")
        self.git(repo_path, "checkout", "main")

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:merge",
            project=project,
            task=task,
            step_id="merge",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "blocked")
        self.assertEqual(task.status, "blocked")
        self.assertIn("only docs or tests changed", task.blocked_reason)

    def test_adequate_verdict_allows_done(self) -> None:
        """A task with partial but real implementation changes can still merge."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()

        project, sprint, task = self.seed_project(
            store,
            repo_path=repo_path,
            acceptance_criteria="Add JWT token generation\nAdd token validation middleware",
        )

        # Implementation covers one criterion, tests present.
        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.write_text(
            repo_path / "auth.py",
            "def generate_token(user_id): return f'token-{user_id}'\n"
            "def validate_token(token): return token.startswith('token-')\n",
        )
        self.write_text(repo_path / "tests/test_auth.py", "def test_generate(): pass\n")
        self.commit_all(repo_path, "feat: partial auth implementation")
        self.git(repo_path, "checkout", "main")

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:merge",
            project=project,
            task=task,
            step_id="merge",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "success")
        self.assertNotEqual(task.status, "blocked")

    def test_completion_guard_emits_event(self) -> None:
        """The merge-time guard emits an engine.completion_guard event with verdict details."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()

        project, sprint, task = self.seed_project(
            store,
            repo_path=repo_path,
            acceptance_criteria="Add auth module",
        )

        # Docs-only changes trigger the guard event.
        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.write_text(repo_path / "docs" / "auth.md", "# Auth module\n")
        self.commit_all(repo_path, "docs: outline auth module")
        self.git(repo_path, "checkout", "main")

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:merge",
            project=project,
            task=task,
            step_id="merge",
            carried_output=None,
            store=store,
        )

        self.assertEqual(len(result.events), 1)
        guard_event = result.events[0]
        self.assertEqual(guard_event.event_type, "engine.completion_guard")
        self.assertIn("verdict", guard_event.payload)
        self.assertIsInstance(guard_event.payload["verdict"], str)


class SprintAdvancementTests(unittest.TestCase):
    """Tests for sprint-41: orchestrator sprint completion and auto-advancement."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.store.initialize()

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _make_project(self, autonomy_level: str = "directed") -> Project:
        p = Project(
            id=f"proj-adv-{autonomy_level}",
            name=f"Test {autonomy_level}",
            repo_path=self.tmp.name,
            workflow_id="development",
            autonomy_level=autonomy_level,  # type: ignore[arg-type]
        )
        self.store.save_project(p)
        return p

    def _make_sprint(self, project_id: str, *, order_index: int = 0, status: str = "planned") -> Sprint:
        s = Sprint(
            id=f"sprint-adv-{project_id}-{order_index}",
            project_id=project_id,
            title=f"Sprint {order_index}",
            status=status,  # type: ignore[arg-type]
            order_index=order_index,
        )
        self.store.save_sprint(s)
        return s

    def _make_done_task(self, sprint: Sprint) -> Task:
        t = Task(
            id=f"task-adv-{sprint.id}",
            sprint_id=sprint.id,
            project_id=sprint.project_id,
            title="Done task",
            status="done",
        )
        self.store.save_task(t)
        return t

    def _orchestrator(self) -> ForemanOrchestrator:
        from foreman.roles import load_roles, default_roles_dir
        from foreman.workflows import load_workflows, default_workflows_dir
        roles = load_roles(default_roles_dir())
        workflows = load_workflows(default_workflows_dir(), available_role_ids=set(roles))
        return ForemanOrchestrator(self.store, roles=roles, workflows=workflows)

    def test_directed_completes_sprint_and_stops(self) -> None:
        project = self._make_project("directed")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        sprint1 = self._make_sprint(project.id, order_index=1, status="planned")
        self._make_done_task(sprint0)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "sprint_complete")
        self.assertIsNone(self.store.get_active_sprint(project.id))
        s0 = next(s for s in self.store.list_sprints(project.id) if s.id == sprint0.id)
        self.assertEqual(s0.status, "completed")
        s1 = next(s for s in self.store.list_sprints(project.id) if s.id == sprint1.id)
        self.assertEqual(s1.status, "planned")

    def test_directed_idle_when_no_next_sprint(self) -> None:
        project = self._make_project("directed")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "idle")
        s = next(s for s in self.store.list_sprints(project.id) if s.id == sprint.id)
        self.assertEqual(s.status, "completed")

    def test_supervised_emits_sprint_ready_event(self) -> None:
        project = self._make_project("supervised")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        sprint1 = self._make_sprint(project.id, order_index=1, status="planned")
        task = self._make_done_task(sprint0)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "sprint_complete")
        event_types = [e.event_type for e in self.store.list_events(task_id=task.id)]
        self.assertIn("engine.sprint_completed", event_types)
        self.assertIn("engine.sprint_ready", event_types)
        ready = next(e for e in self.store.list_events(task_id=task.id) if e.event_type == "engine.sprint_ready")
        self.assertEqual(ready.payload["sprint_id"], sprint1.id)

    def test_directed_does_not_emit_sprint_ready(self) -> None:
        project = self._make_project("directed")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        self._make_sprint(project.id, order_index=1, status="planned")
        task = self._make_done_task(sprint0)

        self._orchestrator().run_project(project.id)

        event_types = [e.event_type for e in self.store.list_events(task_id=task.id)]
        self.assertNotIn("engine.sprint_ready", event_types)
        self.assertIn("engine.sprint_completed", event_types)

    def test_autonomous_activates_next_sprint(self) -> None:
        project = self._make_project("autonomous")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        sprint1 = self._make_sprint(project.id, order_index=1, status="planned")
        self._make_done_task(sprint0)

        result = self._orchestrator().run_project(project.id)

        s1 = next(s for s in self.store.list_sprints(project.id) if s.id == sprint1.id)
        self.assertEqual(s1.status, "active")
        self.assertIsNotNone(s1.started_at)
        self.assertEqual(result.stop_reason, "idle")

    def test_autonomous_stops_when_no_next_sprint(self) -> None:
        project = self._make_project("autonomous")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "idle")

    def test_run_project_auto_activates_first_planned_sprint(self) -> None:
        project = self._make_project("directed")
        sprint = self._make_sprint(project.id, order_index=0, status="planned")
        self._make_done_task(sprint)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "idle")
        refreshed = next(s for s in self.store.list_sprints(project.id) if s.id == sprint.id)
        self.assertEqual(refreshed.status, "completed")
        self.assertIsNotNone(refreshed.started_at)
        self.assertIsNotNone(refreshed.completed_at)

    def test_blocked_tasks_prevent_sprint_completion(self) -> None:
        project = self._make_project("autonomous")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        t = Task(
            id="task-adv-blocked",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Blocked task",
            status="blocked",
        )
        self.store.save_task(t)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "blocked")
        s = next(s for s in self.store.list_sprints(project.id) if s.id == sprint.id)
        self.assertEqual(s.status, "active")

    def test_sprint_with_mixed_done_cancelled_is_resolved(self) -> None:
        project = self._make_project("directed")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)
        t = Task(
            id="task-adv-cancelled",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Cancelled task",
            status="cancelled",
        )
        self.store.save_task(t)

        result = self._orchestrator().run_project(project.id)

        s = next(s for s in self.store.list_sprints(project.id) if s.id == sprint.id)
        self.assertEqual(s.status, "completed")
        self.assertEqual(result.stop_reason, "idle")
