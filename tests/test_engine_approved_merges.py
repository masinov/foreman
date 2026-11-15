"""An approved merge is carried out while another task's step is running."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from foreman.models import Task
from foreman.orchestrator import MERGE_STEP_ROLES, ForemanOrchestrator
from foreman.runner.base import AgentEvent, AgentRunConfig
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedNativeRunner


class ApprovedMergeTests(OrchestratorTestCase):
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

    def test_a_merge_approved_during_another_tasks_step_does_not_wait_for_it(self) -> None:
        """Seen on 2026-11-12: an approval made at 18:28:11 waited behind the
        develop step another task had started 19 seconds earlier."""

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, first, second = self._seed_two_tasks(store, repo_path)
            seen: dict[str, object] = {}

            def second_developer(config: AgentRunConfig):
                # While this step runs, a person approves the first task's
                # merge from the dashboard: a decision, recorded and deferred.
                approver = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
                decision = approver.resume_human_gate(first.id, outcome="approve", defer=True)
                seen["deferred"] = decision.deferred
                seen["waiting_at"] = decision.task.workflow_current_step
                # The step's next tick.
                yield AgentEvent("agent.tick", payload={"elapsed_seconds": 1.0})
                seen["first_status_during_step"] = store.get_task(first.id).status
                seen["on_main"] = "feature.txt" in subprocess.run(
                    ["git", "ls-tree", "-r", "--name-only", "main"],
                    cwd=repo_path, capture_output=True, text=True, check=True,
                ).stdout
                work_dir = Path(config.working_dir)
                self.write_text(work_dir / "second.txt", "second\n")
                self.write_text(work_dir / "ready.txt", "ready\n")
                self.commit_all(work_dir, "feat: second task")
                yield AgentEvent(
                    "agent.message", payload={"text": "Done.\nTASK_COMPLETE", "phase": "assistant"}
                )
                yield AgentEvent("agent.completed", payload={"session_id": "dev-2"})

            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(config),
                    2: lambda config: self._native_reviewer_approve(config),
                    3: second_developer,
                    4: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )
            orchestrator.approved_merge_check_seconds = 0.0

            orchestrator.run_project(project.id)

            self.assertTrue(seen["deferred"])
            self.assertEqual(seen["waiting_at"], "merge")
            self.assertEqual(seen["first_status_during_step"], "done")
            self.assertTrue(seen["on_main"])
            # The step that was running carried on and reached its own gate.
            final_second = store.get_task(second.id)
            self.assertEqual(final_second.status, "blocked")
            self.assertEqual(final_second.workflow_current_step, "merge_approval")

    def test_only_the_named_steps_are_run_for_the_other_task(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, first, _ = self._seed_two_tasks(store, repo_path)
            runner = ScriptedNativeRunner({})
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )
            self.assertIsNotNone(orchestrator.leases.acquire(first, project))

            # The task's next step is an agent step: nothing is run, and the
            # task waits there for the queue.
            left = orchestrator.run_task(
                project, self.workflows[project.workflow_id], first, only_roles=MERGE_STEP_ROLES
            )

            self.assertEqual(runner.call_count, 0)
            self.assertEqual(left.status, "in_progress")
            self.assertEqual(left.workflow_current_step, "develop")
            self.assertIsNone(
                store.get_active_lease(
                    project_id=project.id, resource_type="task", resource_id=first.id
                )
            )

    def test_the_check_is_not_made_on_every_tick(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            _, first, _ = self._seed_two_tasks(store, repo_path)
            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
            reads: list[str] = []
            original = store.list_tasks

            def counting(**kwargs):
                reads.append("list")
                return original(**kwargs)

            store.list_tasks = counting  # type: ignore[method-assign]
            for _ in range(50):
                orchestrator._poll_commands(first.id)

            self.assertEqual(len(reads), 1)


if __name__ == "__main__":
    unittest.main()
