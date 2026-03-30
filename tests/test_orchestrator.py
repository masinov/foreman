"""Integration coverage for the persisted Foreman orchestrator loop."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.models import Project, Run, Sprint, Task
from foreman.orchestrator import (
    AgentExecutionResult,
    ForemanOrchestrator,
)
from foreman.runner.base import AgentEvent, AgentRunConfig, InfrastructureError
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
            acceptance_criteria="Task reaches done after review, test, and merge.",
            created_at="2026-03-30T12:15:00Z",
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
                self.assertIn("Branch: feat/task-1-implement-orchestrator-loop", prompt)
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
            self.assertEqual(result.stop_reason, "idle")

            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.branch_name,
                "feat/task-1-implement-orchestrator-loop",
            )
            self.assertIsNotNone(updated_task.completed_at)

            runs = store.list_runs(task_id=task.id)
            self.assertEqual(
                [run.workflow_step for run in runs],
                ["develop", "review", "test", "merge", "done"],
            )
            self.assertEqual(
                [run.outcome for run in runs],
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

    def test_review_feedback_and_test_failures_carry_output_back_into_development(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            executor = ScriptedAgentExecutor({})

            def developer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("Branch: feat/task-1-implement-orchestrator-loop", prompt)
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
                [run.workflow_step for run in store.list_runs(task_id=task.id)],
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
                self.write_text(repo_path / "feature.txt", "implemented\n")
                self.write_text(repo_path / "ready.txt", "ready\n")
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
                [run.workflow_step for run in runs],
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
                [run.workflow_step for run in runs],
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
                branch_name="feat/task-1-resume-after-bootstrap-approval",
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
            self.assertEqual(
                [run.workflow_step for run in runs],
                ["develop", "review", "test", "merge", "done"],
            )
            self.assertEqual(runs[0].session_id, "dev-session")
            self.assertEqual(
                [run.outcome for run in runs],
                ["done", "approve", "success", "success", "success"],
            )

    def test_native_runner_reuses_persistent_developer_sessions_after_review_denial(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
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
                "Unhandled workflow outcome. Requires human review.",
            )

            event_types = [event.event_type for event in store.list_events(task_id=task.id)]
            self.assertEqual(event_types.count("agent.infra_error"), 2)
            self.assertIn("agent.error", event_types)
            runs = store.list_runs(task_id=task.id)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "failed")
            self.assertEqual(runs[0].outcome, "error")

    def test_native_runner_executes_codex_roles_without_an_injected_executor(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "gpt-5.4"
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
                [run.workflow_step for run in runs],
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
                [run.workflow_step for run in runs],
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
                depends_on_task_ids=["task-0"],
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
            prerequisite = Task(
                id="task-0",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Prerequisite",
                status="in_progress",
                created_at="2026-03-30T12:14:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(blocked_task)
            store.save_task(ready_task)
            store.save_task(prerequisite)

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
            self.assertEqual(
                [run.workflow_step for run in runs],
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


if __name__ == "__main__":
    unittest.main()
