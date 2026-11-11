"""Task branches: refresh, conflicts, and what may reach the default branch."""

from __future__ import annotations
import subprocess
import unittest
from foreman.models import Task
from foreman.engine.branch_sync import prepare_task_branch_for_step
from foreman.engine.results import AgentExecutionResult
from foreman.orchestrator import ForemanOrchestrator
from foreman.git import current_branch
from foreman.store import ForemanStore

from engine_support import (
    OrchestratorTestCase,
    ScriptedAgentExecutor,
)


class BranchAndMergeTests(OrchestratorTestCase):
    """Task branches: refresh, conflicts, and what may reach the default branch."""

    def test_merge_conflict_resolution_returns_to_develop_and_back_through_review(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        self.write_text(repo_path / "docs" / "sprints" / "current.md", "base\n")
        self.commit_all(repo_path, "docs: add sprint baseline")

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["completion_guard_enabled"] = False
            project.settings["merge_approval"] = "human"
            store.save_project(project)
            branch = task.branch_name or "feat/task-1"
            self.git(repo_path, "checkout", "-b", branch)
            self.write_text(
                repo_path / "docs" / "sprints" / "current.md",
                "branch update\n",
            )
            self.write_text(repo_path / "ready.txt", "ready\n")
            self.commit_all(repo_path, "docs: branch updates sprint state")
            self.git(repo_path, "checkout", "main")
            executor = ScriptedAgentExecutor({})

            def developer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("Branch: feat/task-1", prompt)
                return AgentExecutionResult(
                    outcome="done",
                    detail="Task docs updated on the branch.",
                )

            def reviewer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Task docs updated on the branch.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved before merge.",
                )

            def developer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                assert carried_output is not None
                self.assertIn("Merge conflict against 'main'.", carried_output)
                self.assertIn("go back through code review", carried_output)
                merge_result = subprocess.run(
                    ["git", "merge", "main"],
                    cwd=self.work_dir(task, repo_path),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(merge_result.returncode, 0)
                self.write_text(
                    self.work_dir(task, repo_path) / "docs" / "sprints" / "current.md",
                    "resolved main + branch update\n",
                )
                self.commit_all(self.work_dir(task, repo_path), "docs: resolve sprint merge conflict")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Resolved the merge conflict against main.",
                )

            def reviewer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Resolved the merge conflict against main.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after conflict resolution.",
                )

            executor.handlers.update(
                {
                    ("developer", 1): developer_one,
                    ("code_reviewer", 1): reviewer_one,
                    ("developer", 2): developer_two,
                    ("code_reviewer", 2): reviewer_two,
                }
            )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            # First pass: develop, test, review, then wait for a person.
            first = orchestrator.run_project(project.id)
            self.assertEqual(first.executed_task_ids, (task.id,))
            paused = store.get_task(task.id)
            assert paused is not None
            self.assertEqual(paused.status, "blocked")
            self.assertEqual(paused.workflow_current_step, "merge_approval")

            # `main` moves while the task waits for a person. The branch was
            # current when develop ran, so it is the merge, not a develop
            # refresh, that discovers the conflict.
            self.git(repo_path, "checkout", "main")
            self.write_text(
                repo_path / "docs" / "sprints" / "current.md",
                "main update\n",
            )
            self.commit_all(repo_path, "docs: main updates sprint state")

            orchestrator.resume_human_gate(task.id, outcome="approve")
            back_at_gate = store.get_task(task.id)
            assert back_at_gate is not None
            self.assertEqual(back_at_gate.status, "blocked")
            self.assertEqual(back_at_gate.workflow_current_step, "merge_approval")

            orchestrator.resume_human_gate(task.id, outcome="approve")
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            step_runs = [
                r
                for r in store.list_runs(task_id=task.id)
                if r.role_id not in {"_builtin:orchestrator", "_builtin:human_gate"}
            ]
            self.assertEqual(
                [r.workflow_step for r in step_runs],
                [
                    "develop", "test", "review", "merge",
                    "develop", "test", "review", "merge", "done",
                ],
            )
            self.assertEqual(
                [r.outcome for r in step_runs],
                [
                    "done", "success", "approve", "conflict",
                    "done", "success", "approve", "success", "success",
                ],
            )
            assert executor.capture("developer", 2).carried_output is not None
            self.assertIn(
                "Merge conflict against 'main'.",
                executor.capture("developer", 2).carried_output,
            )
            transitions = [
                event.payload
                for event in store.list_events(task_id=task.id)
                if event.event_type == "workflow.transition"
            ]
            self.assertIn(
                {
                    "from_step": "merge",
                    "to_step": "develop",
                    "trigger": "completion:conflict",
                },
                transitions,
            )

    def test_merge_conflict_resets_step_visit_budget_for_conflict_resolution_cycle(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        self.write_text(repo_path / "docs" / "sprints" / "current.md", "base\n")
        self.commit_all(repo_path, "docs: add sprint baseline")

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["completion_guard_enabled"] = False
            project.settings["merge_approval"] = "human"
            project.settings["max_step_visits"] = 1
            store.save_project(project)
            branch = task.branch_name or "feat/task-1"
            self.git(repo_path, "checkout", "-b", branch)
            self.write_text(
                repo_path / "docs" / "sprints" / "current.md",
                "branch update\n",
            )
            self.write_text(repo_path / "ready.txt", "ready\n")
            self.commit_all(repo_path, "docs: branch updates sprint state")
            self.git(repo_path, "checkout", "main")
            executor = ScriptedAgentExecutor({})

            def developer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("Branch: feat/task-1", prompt)
                return AgentExecutionResult(
                    outcome="done",
                    detail="Task docs updated on the branch.",
                )

            def reviewer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Task docs updated on the branch.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved before merge.",
                )

            def developer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                assert carried_output is not None
                self.assertIn("Merge conflict against 'main'.", carried_output)
                self.assertIn("go back through code review", carried_output)
                merge_result = subprocess.run(
                    ["git", "merge", "main"],
                    cwd=self.work_dir(task, repo_path),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(merge_result.returncode, 0)
                self.write_text(
                    self.work_dir(task, repo_path) / "docs" / "sprints" / "current.md",
                    "resolved main + branch update\n",
                )
                self.commit_all(self.work_dir(task, repo_path), "docs: resolve sprint merge conflict")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Resolved the merge conflict against main.",
                )

            def reviewer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Resolved the merge conflict against main.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after conflict resolution.",
                )

            executor.handlers.update(
                {
                    ("developer", 1): developer_one,
                    ("code_reviewer", 1): reviewer_one,
                    ("developer", 2): developer_two,
                    ("code_reviewer", 2): reviewer_two,
                }
            )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            # First pass: develop, test, review, then wait for a person.
            first = orchestrator.run_project(project.id)
            self.assertEqual(first.executed_task_ids, (task.id,))
            paused = store.get_task(task.id)
            assert paused is not None
            self.assertEqual(paused.status, "blocked")
            self.assertEqual(paused.workflow_current_step, "merge_approval")

            # `main` moves while the task waits for a person. The branch was
            # current when develop ran, so it is the merge, not a develop
            # refresh, that discovers the conflict.
            self.git(repo_path, "checkout", "main")
            self.write_text(
                repo_path / "docs" / "sprints" / "current.md",
                "main update\n",
            )
            self.commit_all(repo_path, "docs: main updates sprint state")

            orchestrator.resume_human_gate(task.id, outcome="approve")
            back_at_gate = store.get_task(task.id)
            assert back_at_gate is not None
            self.assertEqual(back_at_gate.status, "blocked")
            self.assertEqual(back_at_gate.workflow_current_step, "merge_approval")

            orchestrator.resume_human_gate(task.id, outcome="approve")
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.step_visit_counts,
                {
                    "develop": 1,
                    "test": 1,
                    "review": 1,
                    "merge_approval": 1,
                    "merge": 1,
                    "done": 1,
                },
            )
            reset_events = [
                event.payload
                for event in store.list_events(task_id=task.id)
                if event.event_type == "workflow.step_visit_reset"
            ]
            self.assertIn(
                {
                    "reason": "merge_conflict_recovery",
                    "from_step": "merge",
                    "to_step": "develop",
                },
                reset_events,
            )

    def test_prepare_task_branch_for_conflict_resolution_refreshes_existing_branch(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        self.write_text(repo_path / "docs" / "base.md", "baseline\n")
        self.commit_all(repo_path, "docs: add base docs")

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                branch_name="feat/task-1",
            )
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "feature.txt", "task work\n")
            self.commit_all(repo_path, "feat: task work")

            self.git(repo_path, "checkout", "main")
            self.write_text(repo_path / "notes.txt", "main moved\n")
            self.commit_all(repo_path, "docs: main moves forward")

            carried_output, sync_event = prepare_task_branch_for_step(
                project=project,
                task=task,
                step="develop",
                carried_output="Merge conflict against 'main'.",
            )

            self.assertIsNotNone(carried_output)
            assert carried_output is not None
            self.assertIn("refreshed branch 'feat/task-1'", carried_output)
            self.assertIsNotNone(sync_event)
            assert sync_event is not None
            self.assertEqual(sync_event[0], "engine.branch_sync")
            self.assertEqual(current_branch(repo_path), "feat/task-1")
            self.assertTrue((repo_path / "notes.txt").is_file())
            self.assertIn(
                "Merge branch 'main' into feat/task-1",
                self.git(repo_path, "log", "-1", "--pretty=%s").stdout.strip(),
            )

    def test_develop_visit_refreshes_a_stale_task_branch_from_main(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        self.write_text(repo_path / "docs" / "base.md", "baseline\n")
        self.commit_all(repo_path, "docs: add base docs")

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                branch_name="feat/task-1",
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "feature.txt", "task work\n")
            self.commit_all(repo_path, "feat: task work")
            self.git(repo_path, "checkout", "main")
            self.write_text(repo_path / "notes.txt", "main moved\n")
            self.commit_all(repo_path, "docs: main moves forward")
            self.git(repo_path, "checkout", task.branch_name)

            carried_output, sync_event = prepare_task_branch_for_step(
                project=project,
                task=task,
                step="develop",
                carried_output=None,
            )

            self.assertIsNotNone(sync_event)
            assert sync_event is not None
            self.assertEqual(sync_event[0], "engine.branch_sync")
            self.assertEqual(sync_event[1]["mode"], "refresh")
            self.assertEqual(sync_event[1]["commits_behind"], 1)
            self.assertIn("refreshed branch 'feat/task-1'", carried_output or "")
            self.assertTrue((repo_path / "notes.txt").is_file())
            self.assertEqual(current_branch(repo_path), "feat/task-1")

            # Up to date now: a second visit does nothing and carries nothing.
            again, again_event = prepare_task_branch_for_step(
                project=project,
                task=task,
                step="develop",
                carried_output=None,
            )
            self.assertIsNone(again)
            self.assertIsNone(again_event)

    def test_develop_visit_resumes_on_a_branch_with_an_unconcluded_merge(self) -> None:
        from foreman.git import checkout_branch, merge_in_progress

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        self.write_text(repo_path / "shared.txt", "original\n")
        self.commit_all(repo_path, "chore: shared file")

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                branch_name="feat/task-1",
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "shared.txt", "task version\n")
            self.commit_all(repo_path, "feat: task edit")
            self.git(repo_path, "checkout", "main")
            self.write_text(repo_path / "shared.txt", "main version\n")
            self.commit_all(repo_path, "fix: main edit")
            self.git(repo_path, "checkout", task.branch_name)
            # The previous pass started the merge and was cut off mid-resolution.
            merge = subprocess.run(
                ["git", "merge", "main"], cwd=repo_path, capture_output=True, text=True, check=False
            )
            self.assertNotEqual(merge.returncode, 0)
            self.assertTrue(merge_in_progress(repo_path))

            # The checkout the engine performs before every step must not
            # trip over the unresolved index.
            checkout_branch(repo_path, task.branch_name, create=True, base_branch="main")

            carried_output, sync_event = prepare_task_branch_for_step(
                project=project,
                task=task,
                step="develop",
                carried_output="Merge conflict against 'main'.",
            )

            self.assertIsNotNone(sync_event)
            assert sync_event is not None
            self.assertEqual(sync_event[0], "engine.branch_sync")
            self.assertEqual(sync_event[1]["mode"], "merge_in_progress")
            self.assertIn("MERGE_HEAD", carried_output or "")
            self.assertTrue(
                merge_in_progress(repo_path),
                "the developer's half-resolved merge must survive the visit",
            )
            self.assertEqual(current_branch(repo_path), "feat/task-1")

    def test_develop_visit_hands_a_conflicting_refresh_to_the_developer(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        self.write_text(repo_path / "shared.txt", "original\n")
        self.commit_all(repo_path, "chore: shared file")

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                branch_name="feat/task-1",
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "shared.txt", "task version\n")
            self.commit_all(repo_path, "feat: task edit")
            self.git(repo_path, "checkout", "main")
            self.write_text(repo_path / "shared.txt", "main version\n")
            self.commit_all(repo_path, "fix: main edit")
            self.git(repo_path, "checkout", task.branch_name)

            carried_output, sync_event = prepare_task_branch_for_step(
                project=project,
                task=task,
                step="develop",
                carried_output=None,
            )

            self.assertIsNotNone(sync_event)
            assert sync_event is not None
            self.assertEqual(sync_event[0], "engine.branch_sync_conflict")
            self.assertEqual(sync_event[1]["mode"], "refresh_conflict")
            self.assertIn("conflicts", carried_output or "")
            self.assertEqual(current_branch(repo_path), "feat/task-1")
            self.assertEqual(
                self.git(repo_path, "status", "--porcelain").stdout.strip(),
                "",
                "a failed refresh must be aborted, leaving the tree clean for the developer",
            )

    def test_a_commit_on_the_default_branch_during_a_step_does_not_block_the_task(self) -> None:
        """The operator's branch is theirs: it may move while a task runs."""

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)

            def developer(*, task: Task, prompt: str, carried_output: str | None):
                # Somebody else lands a commit on main while the agent works.
                self.git(repo_path, "checkout", "-q", "--detach", "main")
                self.write_text(repo_path / "operator.txt", "unrelated\n")
                self.git(repo_path, "add", "operator.txt")
                self.git(repo_path, "commit", "-q", "-m", "chore: operator commit")
                self.git(repo_path, "update-ref", "refs/heads/main", "HEAD")
                tree = self.work_dir(task, repo_path)
                (tree / "ready.txt").write_text("ok\n")
                self.commit_all(tree, "feat: implement")
                return AgentExecutionResult(outcome="error", detail="stop after one step")

            self._run_with_developer(store, project, developer)

            self.assertEqual(
                [
                    e
                    for e in store.list_events(task_id=task.id)
                    if e.event_type == "engine.branch_violation"
                ],
                [],
            )
            self.assertNotIn("default branch", store.get_task(task.id).blocked_reason or "")

    def test_task_commits_reaching_the_default_branch_before_the_merge_step_block_the_task(
        self,
    ) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)

            def developer(*, task: Task, prompt: str, carried_output: str | None):
                tree = self.work_dir(task, repo_path)
                (tree / "ready.txt").write_text("ok\n")
                self.commit_all(tree, "feat: unreviewed work")
                # The agent moves main to its own commit, skipping review.
                self.git(tree, "update-ref", "refs/heads/main", "HEAD")
                return AgentExecutionResult(outcome="done", detail="Implemented.")

            orchestrator, executor, _ = self._run_with_developer(store, project, developer)

            stored = store.get_task(task.id)
            self.assertEqual(stored.status, "blocked")
            self.assertIn("before the merge step", stored.blocked_reason)
            self.assertEqual(executor.call_counts.get("code_reviewer", 0), 0)
            violations = [
                e for e in store.list_events(task_id=task.id) if e.event_type == "engine.branch_violation"
            ]
            self.assertEqual(len(violations), 1)
            self.assertEqual(len(violations[0].payload["commits"]), 1)

    def test_commits_a_refresh_brought_in_from_the_default_branch_are_not_the_tasks_own(self) -> None:
        from foreman.git import head_sha, task_commits_on_default_branch

        repo_path, _ = self.create_workspace()
        self.initialize_repo(repo_path)
        start = head_sha(str(repo_path), "refs/heads/main")
        self.git(repo_path, "checkout", "-q", "-b", "feat/x")
        self.write_text(repo_path / "own.txt", "own\n")
        self.commit_all(repo_path, "feat: own work")
        # main moves, then the task branch is refreshed from it
        self.git(repo_path, "checkout", "-q", "main")
        self.write_text(repo_path / "other.txt", "other\n")
        self.commit_all(repo_path, "chore: someone else")
        refreshed = head_sha(str(repo_path), "refs/heads/main")
        self.git(repo_path, "checkout", "-q", "feat/x")
        self.git(repo_path, "merge", "-q", "--no-edit", "main")
        # main moves again
        self.git(repo_path, "checkout", "-q", "main")
        self.write_text(repo_path / "third.txt", "third\n")
        self.commit_all(repo_path, "chore: and again")

        def leaked() -> tuple[str, ...]:
            return task_commits_on_default_branch(
                str(repo_path),
                task_branch="feat/x",
                default_branch="main",
                default_shas_seen=(start, refreshed),
            )

        self.assertEqual(leaked(), ())
        self.git(repo_path, "merge", "-q", "--no-edit", "feat/x")
        self.assertEqual(len(leaked()), 2)  # the task's commit and its refresh merge


if __name__ == "__main__":
    unittest.main()
