"""Integration coverage for the persisted Foreman orchestrator loop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.models import Project, Sprint, Task
from foreman.orchestrator import (
    AgentExecutionResult,
    ForemanOrchestrator,
    OrchestratorError,
)
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
        task_title: str = "Implement orchestrator loop",
        test_command: str = "test -f ready.txt",
    ) -> tuple[Project, Sprint, Task]:
        project = Project(
            id="project-1",
            name="Foreman Demo",
            repo_path=str(repo_path),
            spec_path="docs/specs/engine-design-v3.md",
            workflow_id="development",
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


class HumanGateResumeTests(unittest.TestCase):
    """Tests for human-gate pause and resume behavior."""

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

    def test_human_gate_pauses_task_at_gate_step(self) -> None:
        """Task pauses at human_gate step with persisted workflow state."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Human Gate Test",
                repo_path=str(repo_path),
                spec_path=None,
                methodology="development",
                workflow_id="development_with_architect",
                default_branch="main",
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Human Gate Sprint",
                goal="Test human gate pause and resume",
                status="active",
                created_at="2026-03-30T12:00:00Z",
                started_at="2026-03-30T12:00:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Plan architecture",
                description="Plan the system architecture",
                status="todo",
                task_type="feature",
                priority=1,
                order_index=1,
                acceptance_criteria="Architecture plan approved",
                created_at="2026-03-30T12:00:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)

            roles = load_roles(default_roles_dir())
            workflows = load_workflows(
                default_workflows_dir(),
                available_role_ids=set(roles),
            )

            def architect_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                del carried_output
                self.assertIn("Plan", prompt)
                return AgentExecutionResult(
                    outcome="done",
                    detail="Architecture plan completed.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=roles,
                workflows=workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("architect", 1): architect_handler,
                    }
                ),
            )

            # Run until human gate pauses
            orchestrator.run_project(project.id)

            paused_task = store.get_task(task.id)
            self.assertIsNotNone(paused_task)
            assert paused_task is not None

            # Task should be paused at human_approval step
            self.assertEqual(paused_task.status, "blocked")
            self.assertEqual(paused_task.workflow_current_step, "human_approval")
            self.assertIsNone(paused_task.workflow_carried_output)
            self.assertIn("human", paused_task.blocked_reason.lower())

            # Verify a workflow.paused event was emitted
            events = store.list_events(task_id=task.id)
            paused_events = [
                event for event in events if event.event_type == "workflow.paused"
            ]
            self.assertEqual(len(paused_events), 1)
            self.assertEqual(
                paused_events[0].payload,
                {"step": "human_approval", "reason": "human_gate"},
            )

    def test_approve_resumes_from_human_gate(self) -> None:
        """Approve resumes task from human gate to develop step."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Human Gate Test",
                repo_path=str(repo_path),
                spec_path=None,
                methodology="development",
                workflow_id="development_with_architect",
                default_branch="main",
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Human Gate Sprint",
                goal="Test human gate pause and resume",
                status="active",
                created_at="2026-03-30T12:00:00Z",
                started_at="2026-03-30T12:00:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Plan architecture",
                description="Plan the system architecture",
                status="todo",
                task_type="feature",
                priority=1,
                order_index=1,
                acceptance_criteria="Architecture plan approved",
                created_at="2026-03-30T12:00:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)

            roles = load_roles(default_roles_dir())
            workflows = load_workflows(
                default_workflows_dir(),
                available_role_ids=set(roles),
            )

            def architect_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                del carried_output
                self.assertIn("Plan", prompt)
                return AgentExecutionResult(
                    outcome="done",
                    detail="Architecture plan completed.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=roles,
                workflows=workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("architect", 1): architect_handler,
                    }
                ),
            )

            # Run until human gate pauses
            orchestrator.run_project(project.id)

            # Resume with approve (no agent executor means deferred)
            result = orchestrator.resume_human_gate(
                task.id,
                outcome="approve",
            )

            self.assertEqual(result.decision, "approve")
            self.assertEqual(result.paused_step, "human_approval")
            self.assertEqual(result.next_step, "develop")
            # Since agent_executor is provided, execution continues (not deferred)
            self.assertEqual(result.deferred, False)

            # Task should be in progress (or done/blocked depending on next step)
            resumed_task = store.get_task(task.id)
            self.assertIsNotNone(resumed_task)
            assert resumed_task is not None

            # Verify workflow.resumed event was emitted
            events = store.list_events(task_id=task.id)
            resumed_events = [
                event for event in events if event.event_type == "workflow.resumed"
            ]
            self.assertGreaterEqual(len(resumed_events), 1)
            self.assertEqual(
                resumed_events[0].payload["decision"],
                "approve",
            )

            # Verify a decision run was created
            decision_runs = [
                run
                for run in store.list_runs(task_id=task.id)
                if run.role_id == "_builtin:human_gate"
            ]
            self.assertGreaterEqual(len(decision_runs), 1)
            # The last decision run should be the approve decision
            self.assertEqual(decision_runs[-1].outcome, "approve")

    def test_deny_resumes_from_human_gate(self) -> None:
        """Denying task at human gate returns to plan step."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Human Gate Test",
                repo_path=str(repo_path),
                spec_path=None,
                methodology="development",
                workflow_id="development_with_architect",
                default_branch="main",
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Human Gate Sprint",
                goal="Test human gate pause and resume",
                status="active",
                created_at="2026-03-30T12:00:00Z",
                started_at="2026-03-30T12:00:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Plan architecture",
                description="Plan the system architecture",
                status="todo",
                task_type="feature",
                priority=1,
                order_index=1,
                acceptance_criteria="Architecture plan approved",
                created_at="2026-03-30T12:00:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)

            roles = load_roles(default_roles_dir())
            workflows = load_workflows(
                default_workflows_dir(),
                available_role_ids=set(roles),
            )

            def architect_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                del carried_output
                self.assertIn("Plan", prompt)
                return AgentExecutionResult(
                    outcome="done",
                    detail="Architecture plan completed.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=roles,
                workflows=workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("architect", 1): architect_handler,
                    }
                ),
            )

            # Run until human gate pauses
            orchestrator.run_project(project.id)

            # Resume with deny and should return to plan step
            result = orchestrator.resume_human_gate(
                task.id,
                outcome="deny",
                note="The architecture needs more detail.",
            )

            self.assertEqual(result.decision, "deny")
            self.assertEqual(result.paused_step, "human_approval")
            self.assertEqual(result.next_step, "plan")
            # Since agent_executor is provided, execution continues (not deferred)
            self.assertEqual(result.deferred, False)
            self.assertEqual(result.note, "The architecture needs more detail.")

            # Task should be back in progress at plan step
            resumed_task = store.get_task(task.id)
            self.assertIsNotNone(resumed_task)
            assert resumed_task is not None

            # Verify the denial run was created
            deny_runs = [
                run
                for run in store.list_runs(task_id=task.id)
                if run.outcome == "deny"
            ]
            self.assertEqual(len(deny_runs), 1)

    def test_resume_human_gate_errors_for_invalid_state(self) -> None:
        """resume_human_gate raises errors for invalid task states."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Error Test",
                repo_path=str(repo_path),
                spec_path=None,
                methodology="development",
                workflow_id="development",
                default_branch="main",
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Error Sprint",
                goal="Test error conditions",
                status="active",
                created_at="2026-03-30T12:00:00Z",
                started_at="2026-03-30T12:00:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Error Task",
                description="Test error conditions",
                status="todo",
                task_type="feature",
                priority=1,
                order_index=1,
                acceptance_criteria="Errors raised correctly",
                created_at="2026-03-30T12:00:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)

            orchestrator = ForemanOrchestrator(store)

            # Unknown task
            with self.assertRaises(OrchestratorError) as exc:
                orchestrator.resume_human_gate("task-unknown", outcome="approve")
            self.assertIn("Unknown task", str(exc.exception))

            # Task not blocked
            with self.assertRaises(OrchestratorError) as exc:
                orchestrator.resume_human_gate(task.id, outcome="approve")
            self.assertIn("not paused at a human gate", str(exc.exception))

            # Task blocked but not at human gate
            task.status = "blocked"
            task.blocked_reason = "Some other reason"
            task.workflow_current_step = None
            store.save_task(task)

            with self.assertRaises(OrchestratorError) as exc:
                orchestrator.resume_human_gate(task.id, outcome="approve")
            self.assertIn("not paused at a human gate", str(exc.exception))

            # Invalid outcome
            task.workflow_current_step = "develop"
            store.save_task(task)
            with self.assertRaises(OrchestratorError) as exc:
                orchestrator.resume_human_gate(task.id, outcome="maybe")
            self.assertIn("Unsupported human-gate outcome", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
