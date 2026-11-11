"""Shared fixtures for the engine tests.

``RepoTestCase`` gives a test a temporary git repository and the shipped
roles and workflows. ``OrchestratorTestCase`` adds a seeded project and the
scripted agents the workflow tests drive. The scripted executors and runners
stand in for agent backends, so no test launches a real agent.
"""

from __future__ import annotations
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
import subprocess
import tempfile
import unittest
from foreman.models import Project, Run, Sprint, Task
from foreman.engine.results import AgentExecutionResult
from foreman.orchestrator import ForemanOrchestrator
from foreman.runner.base import AgentEvent, AgentRunConfig
from foreman.roles import default_roles_dir, load_roles
from foreman.store import ForemanStore
from foreman.workflows import (
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
    env: dict[str, str]
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
                env=dict(config.env),
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


class _LongStreamingRunner:
    """Scripted runner that yields many ``agent.message`` events before the
    terminal ``agent.completed`` event. Used to exercise the in-step lease
    heartbeat path inside the native event loop.
    """

    _MESSAGE_COUNT = 25

    def run(self, config: AgentRunConfig) -> Iterator[AgentEvent]:
        for index in range(self._MESSAGE_COUNT):
            yield AgentEvent(
                "agent.message",
                payload={"text": f"chunk {index}", "phase": "assistant"},
            )
        yield AgentEvent(
            "agent.completed",
            payload={
                "session_id": "long-session",
                "cost_usd": 0.0,
                "duration_ms": 100,
                "token_count": 10,
            },
        )


class RepoTestCase(unittest.TestCase):
    """A temporary git repository plus the shipped roles and workflows."""

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


class OrchestratorTestCase(unittest.TestCase):
    """A seeded project in a temporary repository, and scripted agents to run it."""

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

    def work_dir(self, task: Task, repo_path: Path) -> Path:
        """Return the tree the engine handed this task's agent.

        Every agent step runs in the task's own git worktree, so a fake agent
        that edits files has to edit *that* tree — a file written into the
        operator's checkout would never reach the task branch. Falls back to
        the repository for the few fixtures that run before a worktree exists.
        """

        return Path(task.worktree_path) if task.worktree_path else repo_path

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

    def _run_with_developer(self, store, project, handler):
        executor = ScriptedAgentExecutor({("developer", 1): handler})
        orchestrator = ForemanOrchestrator(
            store, roles=self.roles, workflows=self.workflows, agent_executor=executor
        )
        return orchestrator, executor, orchestrator.run_project(project.id)

    def _native_developer_success(
        self,
        config: AgentRunConfig,
    ) -> tuple[AgentEvent, ...]:
        # The engine hands the runner the task's own worktree; committing
        # anywhere else would not land on the task branch.
        work_dir = Path(config.working_dir)
        self.assertIn("## Task: Implement orchestrator loop", config.prompt)
        self.write_text(work_dir / "feature.txt", "implemented\n")
        self.write_text(work_dir / "ready.txt", "ready\n")
        self.commit_all(work_dir, "feat: implement workflow slice with native runner")
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
        config: AgentRunConfig,
    ) -> tuple[AgentEvent, ...]:
        work_dir = Path(config.working_dir)
        self.assertIsNone(config.session_id)
        self.write_text(work_dir / "feature.txt", "initial implementation\n")
        self.write_text(work_dir / "ready.txt", "ready\n")
        self.commit_all(work_dir, "feat: initial native runner implementation")
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
        config: AgentRunConfig,
    ) -> tuple[AgentEvent, ...]:
        work_dir = Path(config.working_dir)
        self.assertEqual(config.session_id, "dev-session")
        self.write_text(work_dir / "feature.txt", "updated after review\n")
        self.write_text(work_dir / "ready.txt", "ready\n")
        self.commit_all(work_dir, "fix: address review feedback with native runner")
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
        config: AgentRunConfig,
        *,
        expected_session_id: str,
    ) -> tuple[AgentEvent, ...]:
        work_dir = Path(config.working_dir)
        self.assertEqual(config.session_id, expected_session_id)
        self.write_text(work_dir / "feature.txt", "resumed implementation\n")
        self.write_text(work_dir / "ready.txt", "ready\n")
        self.commit_all(work_dir, "fix: resume native runner session")
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
