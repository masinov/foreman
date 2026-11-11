"""Autonomous task selection: the agent names its own task (spec §6.2).

Covers what the engine does when the agent reports its task with
``signal.task_started``, when it never does, and when what it reports cannot
be accepted.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.models import Project, Sprint
from foreman.engine.selection import AUTONOMOUS_PLACEHOLDER_TITLE
from foreman.orchestrator import ForemanOrchestrator
from foreman.runner.base import AgentEvent, AgentRunConfig
from foreman.store import ForemanStore


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {repo}\n{result.stdout}\n{result.stderr}"
        )
    return result


class _ScriptedRunner:
    def __init__(self, behaviours) -> None:
        self._behaviours = list(behaviours)
        self.calls = 0

    def run(self, config: AgentRunConfig):
        self.calls += 1
        yield from self._behaviours.pop(0)(config)


def _commit_work(config: AgentRunConfig) -> None:
    work_dir = Path(config.working_dir)
    (work_dir / "feature.py").write_text("def feature():\n    return 1\n", encoding="utf-8")
    (work_dir / "ready.txt").write_text("ready\n", encoding="utf-8")
    git(work_dir, "add", ".")
    git(work_dir, "commit", "-m", "feat: implement the feature")


def _developer(signal: dict | None):
    def behaviour(config: AgentRunConfig):
        _commit_work(config)
        yield AgentEvent("agent.started", payload={"command": "fake"})
        if signal is not None:
            yield AgentEvent("signal.task_started", payload=signal)
        yield AgentEvent(
            "agent.message",
            payload={"text": "Implemented the feature.\nTASK_COMPLETE", "phase": "result"},
        )
        yield AgentEvent("agent.completed", payload={"session_id": "s"})

    return behaviour


def _reviewer_approves(config: AgentRunConfig):
    yield AgentEvent("agent.started", payload={"command": "fake"})
    yield AgentEvent(
        "agent.message", payload={"text": "The diff is sound.\n\nAPPROVE", "phase": "result"}
    )
    yield AgentEvent("agent.completed", payload={"session_id": "s"})


class AutonomousModeTests(unittest.TestCase):
    def workspace(self) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init")
        git(repo, "checkout", "-b", "main")
        git(repo, "config", "user.email", "autonomous-tests@example.com")
        git(repo, "config", "user.name", "Autonomous Tests")
        (repo / "README.md").write_text("# repo\n", encoding="utf-8")
        (repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "chore: initial commit")
        return repo, root / "foreman.db"

    def run_one(self, developer_signal: dict | None, *, guard: bool = False):
        repo, db_path = self.workspace()
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()
        project = Project(
            id="p1",
            name="Autonomous",
            repo_path=str(repo),
            workflow_id="development",
            default_branch="main",
            settings={
                "task_selection_mode": "autonomous",
                "max_autonomous_tasks": 1,
                "test_command": "test -f ready.txt",
                "default_model": "m",
                "completion_guard_enabled": guard,
            },
        )
        store.save_project(project)
        store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        runner = _ScriptedRunner([_developer(developer_signal), _reviewer_approves])
        orchestrator = ForemanOrchestrator(store, agent_runners={"claude_code": runner})

        orchestrator.run_project(project.id)

        tasks = store.list_tasks(project_id=project.id)
        self.assertEqual(len(tasks), 1)
        return store, tasks[0], runner, repo

    def events(self, store: ForemanStore, task_id: str, event_type: str):
        return [
            event
            for event in store.list_events(task_id=task_id)
            if event.event_type == event_type
        ]

    def test_the_agent_names_its_task(self) -> None:
        store, task, runner, _ = self.run_one(
            {
                "title": "Add the feature module",
                "task_type": "fix",
                "criteria": "feature() returns 1",
            }
        )

        self.assertEqual(task.title, "Add the feature module")
        self.assertEqual(task.task_type, "fix")
        self.assertEqual(task.acceptance_criteria, "feature() returns 1")
        self.assertEqual(task.status, "done")
        self.assertEqual(self.events(store, task.id, "workflow.autonomous_contract_missing"), [])

    def test_an_agent_that_never_names_its_task_is_reviewed_anyway(self) -> None:
        store, task, runner, _ = self.run_one(None)

        # Spec §6.2: degraded but functional. The reviewer still ran and the
        # work went on; the gap is on record once.
        self.assertEqual(runner.calls, 2)
        self.assertEqual(task.title, AUTONOMOUS_PLACEHOLDER_TITLE)
        self.assertEqual(task.status, "done")
        missing = self.events(store, task.id, "workflow.autonomous_contract_missing")
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].payload["step"], "develop")

    def test_without_criteria_the_merge_guard_is_what_stops_an_unnamed_task(self) -> None:
        store, task, runner, _ = self.run_one(None, guard=True)

        self.assertEqual(runner.calls, 2, "review must still happen")
        self.assertEqual(task.status, "blocked")
        self.assertIn("No acceptance criteria defined", task.blocked_reason)

    def test_a_reported_branch_that_is_the_default_branch_is_refused(self) -> None:
        store, task, _, _ = self.run_one(
            {"title": "Sneak onto main", "branch": "main", "criteria": "c"}
        )

        self.assertNotEqual(task.branch_name, "main")
        refused = self.events(store, task.id, "signal.rejected")
        self.assertEqual(len(refused), 1)
        self.assertEqual(refused[0].payload["field"], "branch")
        self.assertIn("default branch", refused[0].payload["reason"])
        # The rest of the signal is still taken.
        self.assertEqual(task.title, "Sneak onto main")

    def test_a_reported_branch_that_is_not_a_branch_name_is_refused(self) -> None:
        for branch in ("feat/..bad", "--upload-pack=x", "feat/never-created"):
            with self.subTest(branch=branch):
                store, task, _, _ = self.run_one(
                    {"title": "Named", "branch": branch, "criteria": "c"}
                )
                self.assertNotEqual(task.branch_name, branch)
                refused = self.events(store, task.id, "signal.rejected")
                self.assertEqual([event.payload["field"] for event in refused], ["branch"])

    def test_an_unknown_task_type_is_refused_and_the_type_kept(self) -> None:
        store, task, _, _ = self.run_one(
            {"title": "Named", "task_type": "improvement", "criteria": "c"}
        )

        self.assertEqual(task.task_type, "feature")
        refused = self.events(store, task.id, "signal.rejected")
        self.assertEqual([event.payload["field"] for event in refused], ["task_type"])


if __name__ == "__main__":
    unittest.main()
