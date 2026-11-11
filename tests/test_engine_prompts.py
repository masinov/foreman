"""What reviewers are told, and what built-in steps log."""

from __future__ import annotations
from pathlib import Path
import unittest
from foreman.models import Project, Run, Sprint, Task
from foreman.orchestrator import ForemanOrchestrator
from foreman.store import ForemanStore

from engine_support import (
    RepoTestCase,
)


class ReviewerPromptHardeningTests(RepoTestCase):
    """Regression coverage for reviewer prompt hardening with engine-produced evidence.

    Proves that the real review path (code_reviewer role) receives structured
    completion evidence from the engine rather than relying solely on
    developer summaries and raw git context.

    Scenarios covered:
    - completion_evidence appears in reviewer prompts when branch_name is set
    - completion_evidence content (not header) is absent when no branch exists
    - completion_evidence is absent from non-reviewer role prompts (developer)
    - evidence section contains verdict and score
    - evidence section appears before the Git Status section
    - weak evidence verdict is visible in the rendered prompt
    - evidence section includes criteria coverage counts
    """

    def seed_project(
        self,
        store: ForemanStore,
        *,
        repo_path: Path,
        acceptance_criteria: str | None = None,
        branch_name: str | None = "feat/test",
    ) -> tuple[Project, Sprint, Task]:
        project = Project(
            id="project-reviewer",
            name="Reviewer Prompt Test",
            repo_path=str(repo_path),
            spec_path="docs/specs/engine-design-v3.md",
            workflow_id="development",
            default_branch="main",
            settings={"task_selection_mode": "directed", "default_model": "gpt-5.4"},
            created_at="2026-04-22T10:00:00Z",
            updated_at="2026-04-22T10:00:00Z",
        )
        sprint = Sprint(
            id="sprint-reviewer",
            project_id=project.id,
            title="Reviewer Sprint",
            goal="Validate reviewer prompts",
            status="active",
            order_index=1,
            created_at="2026-04-22T10:05:00Z",
            started_at="2026-04-22T10:10:00Z",
        )
        task = Task(
            id="task-reviewer-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Implement the queue module",
            description="Build a persistent task queue.",
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
            id=f"run-reviewer-{len(store.list_runs(task_id=task.id)) + 1}",
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

    def _render_reviewer_prompt(
        self,
        store: ForemanStore,
        project: Project,
        task: Task,
        carried_output: str | None = None,
    ) -> str:
        """Render the reviewer prompt for one task using the orchestrator's prompt builder."""
        from foreman.context import build_project_context

        orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
        context_proj = build_project_context(
            store, project, current_task=task, carried_output=carried_output
        )
        reviewer_role = self.roles["code_reviewer"]
        prompt = orchestrator.prompts.build(
            reviewer_role,
            project,
            task,
            carried_output=carried_output,
            context_projection=context_proj,
        )
        return prompt

    def test_completion_evidence_appears_in_reviewer_prompt_when_branch_set(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the queue.\nAdd tests for it.",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the queue module and tests.",
                created_at="2026-04-22T10:20:00Z",
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "queue.py", "def queue(): pass\n")
            self.commit_all(repo_path, "feat: implement queue")
            self.git(repo_path, "checkout", "main")

            prompt = self._render_reviewer_prompt(store, project, task)

            self.assertIn("Completion Evidence", prompt)
            self.assertIn("engine-produced", prompt)

    def test_completion_evidence_content_absent_when_no_branch(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the queue.\nAdd tests for it.",
                branch_name=None,
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the queue module.",
                created_at="2026-04-22T10:20:00Z",
            )

            prompt = self._render_reviewer_prompt(store, project, task)

            # No branch_name means no evidence content. The section header may
            # still render but the substantive evidence is absent.
            self.assertNotIn("Tests: ", prompt)
            self.assertNotIn("Acceptance criteria: ", prompt)

    def test_completion_evidence_absent_from_developer_prompt(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the queue.",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the queue module.",
                created_at="2026-04-22T10:20:00Z",
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "queue.py", "def queue(): pass\n")
            self.commit_all(repo_path, "feat: implement queue")
            self.git(repo_path, "checkout", "main")

            # Render developer prompt — completion_evidence is not a developer role variable
            from foreman.context import build_project_context

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
            context_proj = build_project_context(
                store, project, current_task=task, carried_output=None
            )
            developer_role = self.roles["developer"]
            prompt = orchestrator.prompts.build(
                developer_role,
                project,
                task,
                carried_output=None,
                context_projection=context_proj,
            )

            # completion_evidence only applies to code_reviewer
            self.assertNotIn("Completion Evidence", prompt)

    def test_evidence_section_states_test_and_review_facts(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the queue.\nAdd tests.",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the queue and tests.",
                created_at="2026-04-22T10:20:00Z",
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "queue.py", "def queue(): pass\n")
            self.commit_all(repo_path, "feat: implement queue")
            self.git(repo_path, "checkout", "main")

            prompt = self._render_reviewer_prompt(store, project, task)

            self.assertIn("Tests: not run", prompt)
            self.assertIn("Code review: none yet", prompt)
            self.assertIn("Branch head: ", prompt)
            self.assertNotIn("Evidence score", prompt)

    def test_evidence_section_before_git_status_in_reviewer_prompt(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the queue.",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the queue.",
                created_at="2026-04-22T10:20:00Z",
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "queue.py", "def queue(): pass\n")
            self.commit_all(repo_path, "feat: implement queue")
            self.git(repo_path, "checkout", "main")

            prompt = self._render_reviewer_prompt(store, project, task)

            # In the TOML template, evidence section appears before ### Git Status
            evidence_pos = prompt.find("Completion Evidence (engine-produced)")
            git_status_pos = prompt.find("### Git Status")
            self.assertNotEqual(evidence_pos, -1)
            self.assertNotEqual(git_status_pos, -1)
            self.assertLess(evidence_pos, git_status_pos)

    def test_no_branch_no_evidence_content_in_reviewer_prompt(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            # Task with no branch — build_completion_evidence returns verdict=insufficient
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the queue.\nAdd tests.\nWrite docs.",
                branch_name=None,
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Worked on it.",
                created_at="2026-04-22T10:20:00Z",
            )

            prompt = self._render_reviewer_prompt(store, project, task)

            # Section header may appear (static TOML) but no substantive evidence
            self.assertNotIn("Tests: ", prompt)
            self.assertNotIn("Acceptance criteria: ", prompt)

    def test_evidence_section_includes_criteria_coverage_counts(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the queue.\nAdd tests.\nWrite docs.",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the queue module.",
                created_at="2026-04-22T10:20:00Z",
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "queue.py", "def queue(): pass\n")
            self.commit_all(repo_path, "feat: implement queue")
            self.git(repo_path, "checkout", "main")

            prompt = self._render_reviewer_prompt(store, project, task)

            # The evidence says how many criteria there are and that no judge
            # checked them, rather than claiming coverage.
            self.assertIn("Acceptance criteria: ", prompt)
            self.assertIn("not checked by a judge model", prompt)


class BuiltinTranscriptLoggingTests(RepoTestCase):
    """Coverage for persisted builtin transcript events."""

    def test_run_tests_returns_full_output_events_without_streaming(self) -> None:
        repo_path, _ = self.create_workspace()
        project = Project(
            id="proj-builtins",
            name="Builtin Transcript Test",
            repo_path=str(repo_path),
            spec_path="docs/specs/engine-design-v3.md",
            workflow_id="development",
            default_branch="main",
            settings={
                "test_command": "printf 'stdout-line\\n'; printf 'stderr-line\\n' >&2; exit 1",
            },
            created_at="2026-04-24T18:00:00Z",
            updated_at="2026-04-24T18:00:00Z",
        )
        task = Task(
            id="task-builtins",
            sprint_id="sprint-builtins",
            project_id=project.id,
            title="Capture builtin transcript",
            status="in_progress",
            created_at="2026-04-24T18:00:00Z",
        )

        from foreman.builtins import BuiltinExecutor

        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:run_tests",
            project=project,
            task=task,
            step_id="test",
            carried_output=None,
        )

        self.assertEqual(result.outcome, "failure")
        self.assertEqual(
            [event.event_type for event in result.events],
            ["engine.test_started", "engine.test_output", "engine.test_output", "engine.test_run"],
        )
        output_streams = {
            event.payload.get("stream")
            for event in result.events
            if event.event_type == "engine.test_output"
        }
        self.assertEqual(output_streams, {"stdout", "stderr"})
        final_payload = result.events[-1].payload
        self.assertEqual(final_payload["exit_code"], 1)
        self.assertEqual(final_payload["stdout"], "stdout-line")
        self.assertEqual(final_payload["stderr"], "stderr-line")

    def test_run_tests_streams_events_to_recorder_when_present(self) -> None:
        repo_path, _ = self.create_workspace()
        project = Project(
            id="proj-builtins-stream",
            name="Builtin Transcript Stream Test",
            repo_path=str(repo_path),
            spec_path="docs/specs/engine-design-v3.md",
            workflow_id="development",
            default_branch="main",
            settings={
                "test_command": "printf 'stdout-line\\n'; printf 'stderr-line\\n' >&2; exit 0",
            },
            created_at="2026-04-24T18:00:00Z",
            updated_at="2026-04-24T18:00:00Z",
        )
        task = Task(
            id="task-builtins-stream",
            sprint_id="sprint-builtins-stream",
            project_id=project.id,
            title="Capture streamed builtin transcript",
            status="in_progress",
            created_at="2026-04-24T18:00:00Z",
        )

        from foreman.builtins import BuiltinEventRecord, BuiltinExecutor

        recorded: list[BuiltinEventRecord] = []
        executor = BuiltinExecutor()
        result = executor.execute(
            "_builtin:run_tests",
            project=project,
            task=task,
            step_id="test",
            carried_output=None,
            event_recorder=recorded.append,
        )

        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.events, ())
        self.assertEqual(recorded[0].event_type, "engine.test_started")
        self.assertEqual(recorded[-1].event_type, "engine.test_run")
        self.assertEqual(recorded[-1].payload["exit_code"], 0)
        output_streams = {
            event.payload.get("stream")
            for event in recorded
            if event.event_type == "engine.test_output"
        }
        self.assertEqual(output_streams, {"stdout", "stderr"})

    def test_persisted_streamed_builtin_events_include_schema_version(self) -> None:
        repo_path, db_path = self.create_workspace()

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="proj-builtins-persist",
                name="Builtin Persist Test",
                repo_path=str(repo_path),
                spec_path="docs/specs/engine-design-v3.md",
                workflow_id="development",
                default_branch="main",
                created_at="2026-04-24T18:05:00Z",
                updated_at="2026-04-24T18:05:00Z",
            )
            sprint = Sprint(
                id="sprint-builtins-persist",
                project_id=project.id,
                title="Builtin persist",
                status="active",
                order_index=1,
                created_at="2026-04-24T18:05:00Z",
            )
            task = Task(
                id="task-builtins-persist",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Persist streamed builtin event",
                status="in_progress",
                created_at="2026-04-24T18:05:00Z",
            )
            run = Run(
                id="run-builtins-persist",
                task_id=task.id,
                project_id=project.id,
                role_id="_builtin:run_tests",
                workflow_step="test",
                agent_backend="builtin",
                status="running",
                created_at="2026-04-24T18:05:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)
            store.save_run(run)

            from foreman.builtins import BuiltinEventRecord

            orchestrator = ForemanOrchestrator(store)
            orchestrator._persist_builtin_event(
                run,
                BuiltinEventRecord(
                    event_type="engine.test_output",
                    payload={"stream": "stdout", "text": "line"},
                ),
            )

            events = store.list_events(run_id=run.id)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].payload["schema_version"], "1.0")


if __name__ == "__main__":
    unittest.main()
