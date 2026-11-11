"""The merge and mark-done guards."""

from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import unittest
from foreman.models import CompletionEvidence, Event, Project, Run, Sprint, Task
from foreman.orchestrator import ForemanOrchestrator
from foreman.store import ForemanStore

from engine_support import (
    RepoTestCase,
)


class CompletionGuardTests(RepoTestCase):
    """Regression coverage for the _builtin:mark_done completion guard.

    Verifies that tasks with strong/adequate completion evidence are marked
    done, while tasks with weak/insufficient evidence are blocked and their
    blocked_reason is set to explain the weak verdict.
    """

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

    def seed_passing_completion_evidence(self, store: ForemanStore, project: Project, task: Task) -> None:
        detail = (
            "Implemented Add JWT token generation and Add token validation middleware. "
            "Tests pass for both acceptance criteria."
        )
        store.save_run(
            Run(
                id="run-guard-develop",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="test",
                status="completed",
                outcome="done",
                outcome_detail=detail,
                branch_name=task.branch_name,
                created_at="2026-04-22T10:20:00Z",
                completed_at="2026-04-22T10:21:00Z",
            )
        )
        store.save_run(
            Run(
                id="run-guard-review",
                task_id=task.id,
                project_id=project.id,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="test",
                status="completed",
                outcome="approve",
                outcome_detail="APPROVE",
                branch_name=task.branch_name,
                created_at="2026-04-22T10:22:00Z",
                completed_at="2026-04-22T10:23:00Z",
            )
        )
        test_run = Run(
            id="run-guard-test",
            task_id=task.id,
            project_id=project.id,
            role_id="_builtin:run_tests",
            workflow_step="test",
            agent_backend="builtin",
            status="completed",
            outcome="success",
            outcome_detail="Tests passed.",
            branch_name=task.branch_name,
            created_at="2026-04-22T10:24:00Z",
            completed_at="2026-04-22T10:25:00Z",
        )
        store.save_run(test_run)
        store.save_event(
            Event(
                id="event-guard-test",
                run_id=test_run.id,
                task_id=task.id,
                project_id=project.id,
                event_type="engine.test_run",
                payload={
                    "schema_version": "1.0",
                    "command": "test -f ready.txt",
                    "exit_code": 0,
                    "passed": True,
                    "stdout": "",
                    "stderr": "",
                    "output_tail": "passed",
                },
                timestamp="2026-04-22T10:25:00Z",
            )
        )

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
        self.seed_passing_completion_evidence(store, project, task)

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
        self.assertIn("Blocking merge because", task.blocked_reason)
        self.assertNotIn("verdict", task.blocked_reason)

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

    def test_partial_criteria_blocks_done(self) -> None:
        """A task with only partial criteria coverage is blocked by the proof gate."""
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

        self.assertEqual(result.outcome, "blocked")
        self.assertEqual(task.status, "blocked")
        self.assertIn("Completion proof not passed", result.detail)

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
        self.assertNotIn("verdict", guard_event.payload)
        self.assertNotIn("score", guard_event.payload)
        self.assertIn(guard_event.payload["proof_status"], ("pending", "failed"))
        self.assertIsInstance(guard_event.payload["reasons"], list)

    def test_merge_blocks_dirty_uncommitted_task_work(self) -> None:
        """_builtin:merge refuses to carry dirty task-branch changes onto main."""
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

        from foreman.builtins import BuiltinExecutor
        from foreman.worktrees import WorktreeManager

        worktree = WorktreeManager(project).ensure(task)
        task.worktree_path = str(worktree)
        self.write_text(worktree / "auth.py", "def issue_token(user_id): return f'token-{user_id}'\n")

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
        self.assertIn("uncommitted changes", result.detail)
        self.assertEqual(task.status, "blocked")
        # The refusal did not move the operator's checkout off its own branch.
        self.assertEqual(self.git(repo_path, "branch", "--show-current").stdout.strip(), "main")

    def test_merge_blocks_branch_without_committed_delta(self) -> None:
        """_builtin:merge refuses success when the task branch has no commits ahead of main."""
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

        self.git(repo_path, "checkout", "-b", task.branch_name)
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
        self.assertIn("no commits ahead", result.detail)
        self.assertEqual(task.status, "blocked")

    def test_merge_guard_block_emits_evidence_failed_attention(self) -> None:
        """A merge blocked by the completion guard raises exactly one
        engine.attention_needed turn, tagged ``evidence_failed`` because the
        rebuilt proof gate lands ``failed``."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()

        project, sprint, task = self.seed_project(
            store,
            repo_path=repo_path,
            acceptance_criteria="Add auth module with token validation",
        )

        # Docs-only delta on a feature task whose tests failed → the proof
        # gate fails and the merge guard blocks.
        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.write_text(repo_path / "docs" / "auth.md", "# Auth module\n")
        self.commit_all(repo_path, "docs: outline auth module")
        self.git(repo_path, "checkout", "main")
        task.status = "in_progress"
        store.save_task(task)
        store.save_run(
            Run(
                id="run-attention-test",
                task_id=task.id,
                project_id=project.id,
                role_id="_builtin:run_tests",
                workflow_step="test",
                agent_backend="builtin",
                status="completed",
                outcome="failure",
                created_at="2026-04-22T10:24:00Z",
                completed_at="2026-04-22T10:24:30Z",
            )
        )
        store.save_event(
            Event(
                id="event-attention-test",
                run_id="run-attention-test",
                task_id=task.id,
                project_id=project.id,
                event_type="engine.test_run",
                timestamp="2026-04-22T10:24:30Z",
                payload={"command": "pytest", "exit_code": 1, "passed": False},
            )
        )

        orchestrator = ForemanOrchestrator(
            store, roles=self.roles, workflows=self.workflows
        )
        orchestrator.run_workflow_from_step(
            project,
            self.workflows["development"],
            task,
            step="merge",
            carried_output=None,
        )

        attention = [
            e for e in store.list_events(task_id=task.id)
            if e.event_type == "engine.attention_needed"
        ]
        self.assertEqual(len(attention), 1)
        self.assertEqual(attention[0].payload["trigger"], "evidence_failed")
        self.assertEqual(attention[0].payload["task_id"], task.id)
        self.assertEqual(store.get_task(task.id).status, "blocked")

    def test_attention_trigger_for_block_selects_by_proof_status(self) -> None:
        """``_attention_trigger_for_block`` returns ``evidence_failed`` only when
        the task carries failed completion evidence."""

        repo_path, db_path = self.create_workspace()
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()
        orchestrator = ForemanOrchestrator(store)

        base = Task(id="t", sprint_id="s", project_id="p", title="T")
        self.assertEqual(
            orchestrator.records.attention_trigger_for_block(base), "task_blocked"
        )

        failed = replace(
            base,
            completion_evidence=CompletionEvidence(
                task_id="t",
                task_title="T",
                acceptance_criteria="c",
                proof_status="failed",
            ),
        )
        self.assertEqual(
            orchestrator.records.attention_trigger_for_block(failed), "evidence_failed"
        )

        passed = replace(
            base,
            completion_evidence=CompletionEvidence(
                task_id="t",
                task_title="T",
                acceptance_criteria="c",
                proof_status="passed",
            ),
        )
        self.assertEqual(
            orchestrator.records.attention_trigger_for_block(passed), "task_blocked"
        )


class MarkDoneCompletionGuardTests(RepoTestCase):
    """Regression coverage for the _builtin:mark_done completion guard.

    Verifies that _builtin:mark_done blocks tasks with weak/insufficient
    evidence, and allows through strong/adequate evidence, mirroring the
    same guard logic already present in _builtin:merge.
    """

    def seed_project(
        self,
        store: ForemanStore,
        *,
        repo_path: Path,
        acceptance_criteria: str,
    ) -> tuple[Project, Sprint, Task]:
        project = Project(
            id="proj-mark-done",
            name="Mark Done Guard Test",
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
            id="sprint-mark-done",
            project_id=project.id,
            title="Mark Done Guard Sprint",
            status="active",
            order_index=1,
            created_at="2026-04-22T10:05:00Z",
            started_at="2026-04-22T10:10:00Z",
        )
        task = Task(
            id="task-mark-done-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Implement auth tokens",
            description="Build a token-based auth system.",
            status="todo",
            task_type="feature",
            priority=1,
            order_index=1,
            acceptance_criteria=acceptance_criteria,
            branch_name="feat/mark-done-test",
            created_at="2026-04-22T10:15:00Z",
        )
        store.save_project(project)
        store.save_sprint(sprint)
        store.save_task(task)
        return project, sprint, task

    def seed_passing_completion_evidence(self, store: ForemanStore, project: Project, task: Task) -> None:
        detail = (
            "Implemented Add JWT token generation and Add token validation middleware. "
            "Tests pass for both acceptance criteria."
        )
        store.save_run(
            Run(
                id="run-mark-done-develop",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="test",
                status="completed",
                outcome="done",
                outcome_detail=detail,
                branch_name=task.branch_name,
                created_at="2026-04-22T10:20:00Z",
                completed_at="2026-04-22T10:21:00Z",
            )
        )
        store.save_run(
            Run(
                id="run-mark-done-review",
                task_id=task.id,
                project_id=project.id,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="test",
                status="completed",
                outcome="approve",
                outcome_detail="APPROVE",
                branch_name=task.branch_name,
                created_at="2026-04-22T10:22:00Z",
                completed_at="2026-04-22T10:23:00Z",
            )
        )
        test_run = Run(
            id="run-mark-done-test",
            task_id=task.id,
            project_id=project.id,
            role_id="_builtin:run_tests",
            workflow_step="test",
            agent_backend="builtin",
            status="completed",
            outcome="success",
            outcome_detail="Tests passed.",
            branch_name=task.branch_name,
            created_at="2026-04-22T10:24:00Z",
            completed_at="2026-04-22T10:25:00Z",
        )
        store.save_run(test_run)
        store.save_event(
            Event(
                id="event-mark-done-test",
                run_id=test_run.id,
                task_id=task.id,
                project_id=project.id,
                event_type="engine.test_run",
                payload={
                    "schema_version": "1.0",
                    "command": "test -f ready.txt",
                    "exit_code": 0,
                    "passed": True,
                    "stdout": "",
                    "stderr": "",
                    "output_tail": "passed",
                },
                timestamp="2026-04-22T10:25:00Z",
            )
        )

    def test_strong_verdict_allows_mark_done(self) -> None:
        """A task with real implementation changes can be marked done via _builtin:mark_done."""
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

        # Commit real implementation files.
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
        self.seed_passing_completion_evidence(store, project, task)

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:mark_done",
            project=project,
            task=task,
            step_id="done",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "success")
        self.assertEqual(task.status, "done")
        self.assertNotEqual(task.status, "blocked")

    def test_insufficient_verdict_blocks_mark_done(self) -> None:
        """A task with no material implementation changes is blocked by _builtin:mark_done."""
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

        # Only a docs note — no implementation.
        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.write_text(repo_path / "NOTES.md", "Will implement JWT auth next sprint.\n")
        self.commit_all(repo_path, "docs: outline auth approach")
        self.git(repo_path, "checkout", "main")

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:mark_done",
            project=project,
            task=task,
            step_id="done",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "blocked")
        self.assertEqual(task.status, "blocked")
        self.assertIn("Blocking merge because", task.blocked_reason)
        self.assertNotIn("verdict", task.blocked_reason)

    def test_weak_verdict_blocks_mark_done(self) -> None:
        """A docs-only implementation branch is blocked by _builtin:mark_done."""
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
            "_builtin:mark_done",
            project=project,
            task=task,
            step_id="done",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "blocked")
        self.assertEqual(task.status, "blocked")
        self.assertIn("only docs or tests changed", task.blocked_reason)

    def test_partial_criteria_blocks_mark_done(self) -> None:
        """A task with partial criteria coverage is blocked by _builtin:mark_done."""
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
            "_builtin:mark_done",
            project=project,
            task=task,
            step_id="done",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "blocked")
        self.assertEqual(task.status, "blocked")
        self.assertIn("Completion proof not passed", result.detail)

    def test_mark_done_guard_emits_event(self) -> None:
        """The _builtin:mark_done guard emits an engine.completion_guard event on block."""
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
            "_builtin:mark_done",
            project=project,
            task=task,
            step_id="done",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "blocked")
        self.assertEqual(len(result.events), 1)
        guard_event = result.events[0]
        self.assertEqual(guard_event.event_type, "engine.completion_guard")
        self.assertNotIn("verdict", guard_event.payload)
        self.assertNotIn("score", guard_event.payload)
        self.assertIn(guard_event.payload["proof_status"], ("pending", "failed"))
        self.assertIsInstance(guard_event.payload["reasons"], list)

    def test_mark_done_guard_disabled_via_setting(self) -> None:
        """_builtin:mark_done skips the guard when completion_guard_enabled=False."""
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
        # Disable the guard via project settings.
        project.settings["completion_guard_enabled"] = False
        store.save_project(project)

        # Only a docs note — would normally block, but guard is disabled.
        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.write_text(repo_path / "NOTES.md", "Will implement next sprint.\n")
        self.commit_all(repo_path, "docs: outline")
        self.git(repo_path, "checkout", "main")

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:mark_done",
            project=project,
            task=task,
            step_id="done",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "success")
        self.assertEqual(task.status, "done")

    def test_mark_done_non_implementation_task_type_skips_guard(self) -> None:
        """_builtin:mark_done skips the guard for docs/spike/chore task types."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()

        project, sprint, task = self.seed_project(
            store,
            repo_path=repo_path,
            acceptance_criteria="Write documentation for auth module",
        )
        task.task_type = "docs"
        store.save_task(task)

        # Only a docs note — would normally block for feature, but docs type bypasses.
        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.write_text(repo_path / "docs" / "auth.md", "# Auth module\nDocumentation.\n")
        self.commit_all(repo_path, "docs: write auth docs")
        self.git(repo_path, "checkout", "main")

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:mark_done",
            project=project,
            task=task,
            step_id="done",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "success")
        self.assertEqual(task.status, "done")

    def test_mark_done_blocks_dirty_uncommitted_worktree(self) -> None:
        """_builtin:mark_done refuses to finalize a task from dirty branch state."""
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

        from foreman.builtins import BuiltinExecutor
        from foreman.worktrees import WorktreeManager

        worktree = WorktreeManager(project).ensure(task)
        task.worktree_path = str(worktree)
        self.write_text(worktree / "auth.py", "def issue_token(user_id): return f'token-{user_id}'\n")

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:mark_done",
            project=project,
            task=task,
            step_id="done",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "blocked")
        self.assertIn("uncommitted changes", result.detail)
        self.assertEqual(task.status, "blocked")
        # The worktree survives a refusal: the work in it is what needs saving.
        self.assertTrue(worktree.is_dir())

    def test_mark_done_blocks_absorbed_branch_without_successful_merge_run(self) -> None:
        """_builtin:mark_done refuses already-absorbed branches without a recorded merge success."""
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

        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.git(repo_path, "checkout", "main")

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:mark_done",
            project=project,
            task=task,
            step_id="done",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "blocked")
        self.assertIn("no recorded successful merge", result.detail)
        self.assertEqual(task.status, "blocked")

    def test_mark_done_allows_absorbed_branch_with_successful_merge_run(self) -> None:
        """_builtin:mark_done still succeeds after a recorded successful merge."""
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

        self.git(repo_path, "checkout", "-b", task.branch_name)
        self.write_text(repo_path / "auth.py", "def issue_token(user_id): return f'token-{user_id}'\n")
        self.commit_all(repo_path, "feat: implement auth module")
        self.git(repo_path, "checkout", "main")
        self.git(repo_path, "merge", "--no-ff", "--no-edit", task.branch_name)

        store.save_run(
            Run(
                id="run-merge-success",
                task_id=task.id,
                project_id=project.id,
                role_id="_builtin:merge",
                workflow_step="merge",
                agent_backend="builtin",
                status="completed",
                outcome="success",
                outcome_detail="Merged branch into main.",
                created_at="2026-04-22T10:30:00Z",
                completed_at="2026-04-22T10:30:00Z",
            )
        )

        from foreman.builtins import BuiltinExecutor

        task.status = "in_progress"
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:mark_done",
            project=project,
            task=task,
            step_id="done",
            carried_output=None,
            store=store,
        )

        self.assertEqual(result.outcome, "success")
        self.assertEqual(task.status, "done")


if __name__ == "__main__":
    unittest.main()
