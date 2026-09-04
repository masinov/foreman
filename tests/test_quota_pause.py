"""A backend quota running out pauses the task; it does not fail it."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.models import Project, Sprint, Task
from foreman.orchestrator import ForemanOrchestrator
from foreman.runner.base import AgentEvent, AgentRunConfig
from foreman.store import ForemanStore


class _ScriptedRunner:
    def __init__(self, behaviours) -> None:
        self._behaviours = list(behaviours)
        self.prompts: list[str] = []

    def run(self, config: AgentRunConfig):
        self.prompts.append(config.prompt)
        behaviour = self._behaviours.pop(0)
        yield from behaviour(config)


def _quota_hit(config: AgentRunConfig):
    yield AgentEvent("agent.started", payload={"command": "fake"})
    yield AgentEvent("agent.rate_limit", payload={"status": "rejected", "resets_at": 1788528000})
    yield AgentEvent(
        "agent.message",
        payload={"text": "You've hit your session limit · resets 3:20pm", "phase": "result"},
    )
    yield AgentEvent(
        "agent.error",
        payload={
            "error": "You've hit your session limit · resets 3:20pm (Europe/Madrid)",
            "quota_exhausted": True,
            "retry_after": "2026-09-04T13:20:00Z",
            "session_id": "s-quota",
            "cost_usd": 1.46,
            "duration_ms": 56049,
            "token_count": 3707,
        },
    )


def _finishes(text: str):
    def behaviour(config: AgentRunConfig):
        yield AgentEvent("agent.started", payload={"command": "fake"})
        yield AgentEvent("agent.message", payload={"text": text, "phase": "result"})
        yield AgentEvent(
            "agent.completed",
            payload={"session_id": "s-ok", "cost_usd": 0.0, "duration_ms": 1, "token_count": 1},
        )

    return behaviour


class QuotaPauseTests(unittest.TestCase):
    def _workspace(self) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo = root / "repo"
        repo.mkdir()
        for args in (
            ("init",),
            ("checkout", "-b", "main"),
            ("config", "user.email", "t@example.com"),
            ("config", "user.name", "T"),
        ):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        (repo / "README.md").write_text("# r\n", encoding="utf-8")
        (repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
        return repo, root / "foreman.db"

    def _seed(self, store: ForemanStore, repo: Path) -> tuple[Project, Task]:
        project = Project(
            id="p1",
            name="Quota",
            repo_path=str(repo),
            workflow_id="development",
            default_branch="main",
            settings={"task_selection_mode": "directed", "test_command": "true", "default_model": "m"},
        )
        store.save_project(project)
        store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        task = Task(
            id="t1",
            sprint_id="s1",
            project_id="p1",
            title="Implement",
            status="todo",
            acceptance_criteria="Implemented.",
        )
        store.save_task(task)
        return project, task

    def test_quota_exhaustion_pauses_the_task_at_its_step_and_reports_the_reset(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo)
            runner = _ScriptedRunner([_quota_hit])
            orchestrator = ForemanOrchestrator(store, agent_runners={"claude_code": runner})

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "quota_exhausted")
            self.assertEqual(result.retry_after, "2026-09-04T13:20:00Z")
            self.assertIn("session limit", result.detail or "")
            self.assertEqual(result.executed_task_ids, ("t1",))
            self.assertEqual(result.blocked_task_ids, ())

            paused = store.get_task("t1")
            self.assertEqual(paused.status, "in_progress", "a quota is not a task failure")
            self.assertIsNone(paused.blocked_reason)
            self.assertEqual(paused.workflow_current_step, "develop")
            self.assertEqual(
                paused.step_visit_counts.get("develop", 0),
                0,
                "the visit that hit the quota did no work and must not spend loop budget",
            )

            runs = store.list_runs(task_id="t1")
            developer_runs = [run for run in runs if run.role_id == "developer"]
            self.assertEqual(len(developer_runs), 1)
            failed = developer_runs[0]
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.failure_type, "quota")
            self.assertEqual(failed.session_id, "s-quota")
            self.assertAlmostEqual(failed.cost_usd, 1.46)
            self.assertEqual(failed.token_count, 3707)

            event_types = [event.event_type for event in store.list_events(task_id="t1")]
            self.assertIn("engine.quota_exhausted", event_types)
            self.assertNotIn("engine.output_contract_retry", event_types)
            self.assertNotIn("workflow.no_transition", event_types)
            self.assertNotIn("engine.attention_needed", event_types)

            self.assertIsNone(
                store.get_active_lease(project_id="p1", resource_type="task", resource_id="t1"),
                "the paused task must be resumable by the next pass",
            )
            head = subprocess.run(
                ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True, check=True
            ).stdout.strip()
            self.assertEqual(head, "main", "the checkout is restored while the task waits")

    def test_next_pass_resumes_the_paused_task_at_the_same_step(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo)
            runner = _ScriptedRunner(
                [
                    _quota_hit,
                    _finishes("Implemented the feature.\nTASK_COMPLETE"),
                    _finishes("APPROVE"),
                ]
            )
            orchestrator = ForemanOrchestrator(store, agent_runners={"claude_code": runner})

            first = orchestrator.run_project(project.id)
            self.assertEqual(first.stop_reason, "quota_exhausted")

            second = orchestrator.run_project(project.id)

            self.assertNotEqual(second.stop_reason, "quota_exhausted")
            self.assertEqual(second.executed_task_ids, ("t1",))
            steps = [(run.role_id, run.workflow_step, run.outcome) for run in store.list_runs(task_id="t1")]
            self.assertIn(("developer", "develop", "error"), steps)
            self.assertIn(("developer", "develop", "done"), steps)
            self.assertIn(("_builtin:run_tests", "test", "success"), steps)
            self.assertEqual(
                [role for role, _, _ in steps].count("developer"),
                2,
                "the resumed pass runs the developer once more, at the same step",
            )
            self.assertEqual(len(runner.prompts), 3)


if __name__ == "__main__":
    unittest.main()
