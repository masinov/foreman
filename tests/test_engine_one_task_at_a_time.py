"""The engine runs one task at a time (ADR-0039).

A task waiting for a user's decision at a gate holds the queue: no other
task starts until it is decided, and the decided task is carried on first.
So the next task starts from the default branch the last one left.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from foreman.domain.models import Task
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.runner.base import AgentEvent, AgentRunConfig
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedNativeRunner


class OneTaskAtATimeTests(OrchestratorTestCase):
    def _seed_two_tasks(self, store: ForemanStore, repo_path: Path):
        project, sprint, first = self.seed_project(store, repo_path=repo_path)
        project.settings["merge_approval"] = "human"
        store.save_project(project)
        second = Task(
            id="task-2",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Second task",
            status="todo",
            task_type="feature",
            priority=first.priority + 1,
            order_index=first.order_index + 1,
            created_at="2026-03-30T12:20:00Z",
        )
        store.save_task(second)
        return project, first, second

    def _second_developer(self, config: AgentRunConfig):
        """The second task's developer: one file, one commit, done."""

        work_dir = Path(config.working_dir)
        self.write_text(work_dir / "second.txt", "second\n")
        # What the scripted project's test command checks for.
        self.write_text(work_dir / "ready.txt", "ready\n")
        self.commit_all(work_dir, "feat: second task")
        yield AgentEvent("agent.message", payload={"text": "Done.\nTASK_COMPLETE", "phase": "assistant"})
        yield AgentEvent("agent.completed", payload={"session_id": "dev-2"})

    def _orchestrator(self, store: ForemanStore, runner: ScriptedNativeRunner) -> ForemanOrchestrator:
        return ForemanOrchestrator(
            store,
            roles=self.roles,
            workflows=self.workflows,
            agent_runners={"claude_code": runner},
        )

    def test_a_task_waiting_for_a_decision_holds_the_queue(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, first, second = self._seed_two_tasks(store, repo_path)
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(config),
                    2: lambda config: self._native_reviewer_approve(config),
                    3: self._second_developer,
                    4: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = self._orchestrator(store, runner)

            result = orchestrator.run_project(project.id)

            # The first task stopped at its merge approval, and nothing else
            # started: the second task was not touched.
            self.assertEqual(result.stop_reason, "waiting_for_decision")
            waiting = store.get_task(first.id)
            self.assertEqual((waiting.status, waiting.workflow_current_step), ("blocked", "merge_approval"))
            untouched = store.get_task(second.id)
            self.assertEqual(untouched.status, "todo")
            self.assertEqual(store.list_runs(task_id=second.id), [])
            self.assertEqual(runner.call_count, 2)

            # Another pass, with nothing decided, still starts nothing.
            again = orchestrator.run_project(project.id)
            self.assertEqual(again.stop_reason, "waiting_for_decision")
            self.assertEqual(again.executed_task_ids, ())
            self.assertEqual(store.get_task(second.id).status, "todo")

            # A user approves, as the dashboard does: recorded, left for the engine.
            decision = orchestrator.resume_human_gate(first.id, outcome="approve", defer=True)
            self.assertTrue(decision.deferred)

            orchestrator.run_project(project.id)

            # The decided task is merged first; then the second task runs, on
            # a branch that starts from the merge.
            self.assertEqual(store.get_task(first.id).status, "done")
            merge_sha = next(
                event.payload["sha"]
                for event in store.list_events(task_id=first.id)
                if event.event_type == "engine.merge"
            )
            second_now = store.get_task(second.id)
            self.assertEqual((second_now.status, second_now.workflow_current_step), ("blocked", "merge_approval"))
            self.assertEqual(
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", merge_sha, second_now.branch_name],
                    cwd=repo_path,
                ).returncode,
                0,
            )

    def test_a_task_blocked_by_a_failure_does_not_hold_the_queue(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, first, second = self._seed_two_tasks(store, repo_path)
            # Blocked by the engine (a failure), not waiting at a gate: it
            # needs fixing, not a decision.
            first.status = "blocked"
            first.workflow_current_step = "develop"
            first.blocked_reason = "Step visit limit reached."
            store.save_task(first)
            runner = ScriptedNativeRunner(
                {
                    1: self._second_developer,
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = self._orchestrator(store, runner)

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "waiting_for_decision")
            self.assertIn(second.id, result.executed_task_ids)
            self.assertEqual(store.get_task(first.id).status, "blocked")
            self.assertEqual(store.get_task(second.id).workflow_current_step, "merge_approval")


if __name__ == "__main__":
    unittest.main()
