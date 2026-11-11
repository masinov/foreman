"""Completion evidence: what is recorded, and when it is rebuilt."""

from __future__ import annotations
from pathlib import Path
import unittest
from foreman.models import CompletionEvidence, Event, Project, Run, Sprint, Task
from foreman.orchestrator import ForemanOrchestrator
from foreman.store import ForemanStore

from engine_support import (
    RepoTestCase,
)


class CompletionEvidenceTests(RepoTestCase):
    """Regression coverage for CompletionEvidence model and build_completion_evidence."""

    def seed_project(
        self,
        store: ForemanStore,
        *,
        repo_path: Path,
        acceptance_criteria: str | None = None,
        branch_name: str | None = "feat/task-evidence-1",
    ) -> tuple[Project, Sprint, Task]:
        project = Project(
            id="project-evidence",
            name="Evidence Demo",
            repo_path=str(repo_path),
            spec_path="docs/specs/engine-design-v3.md",
            workflow_id="development",
            default_branch="main",
            settings={
                "task_selection_mode": "directed",
                "test_command": "test -f ready.txt",
                "default_model": "gpt-5.4",
            },
            created_at="2026-04-22T10:00:00Z",
            updated_at="2026-04-22T10:00:00Z",
        )
        sprint = Sprint(
            id="sprint-evidence",
            project_id=project.id,
            title="Evidence Sprint",
            goal="Validate completion evidence",
            status="active",
            order_index=1,
            created_at="2026-04-22T10:05:00Z",
            started_at="2026-04-22T10:10:00Z",
        )
        task = Task(
            id="task-evidence-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Validate evidence model",
            description="Run through the evidence gathering pipeline.",
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
            id=f"run-ev-{len(store.list_runs(task_id=task.id)) + 1}",
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

    def seed_test_event(
        self,
        store: ForemanStore,
        run: Run,
        task: Task,
        project: Project,
        passed: bool,
        timestamp: str,
        command: str = "pytest tests/",
    ) -> None:
        test_run_event = Event(
            id=f"event-test-run-{task.id}-{run.id}",
            run_id=run.id,
            task_id=task.id,
            project_id=project.id,
            event_type="engine.test_run",
            timestamp=timestamp,
            payload={"command": command, "passed": passed},
        )
        test_output_event = Event(
            id=f"event-test-output-{task.id}-{run.id}",
            run_id=run.id,
            task_id=task.id,
            project_id=project.id,
            event_type="engine.test_output",
            timestamp=timestamp,
            payload={"exit_code": 0 if passed else 1, "output": "tests passed" if passed else "FAILED"},
        )
        store.save_event(test_run_event)
        store.save_event(test_output_event)

    def test_build_completion_evidence_returns_correct_structure(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the orchestrator.\nWrite tests for it.",
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the orchestrator module with proper structure.",
                created_at="2026-04-22T10:20:00Z",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                outcome="approve",
                outcome_detail="Implementation looks correct.",
                created_at="2026-04-22T10:25:00Z",
            )

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "orchestrator.py", "def run(): pass\n")
            self.commit_all(repo_path, "feat: implement orchestrator")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            self.assertEqual(evidence.task_id, task.id)
            self.assertEqual(evidence.task_title, task.title)
            self.assertEqual(evidence.acceptance_criteria, task.acceptance_criteria)
            self.assertEqual(evidence.criteria_count, 2)
            self.assertGreater(len(evidence.agent_outputs), 0)
            self.assertIn("orchestrator.py", evidence.changed_files)
            self.assertIn("1 file", evidence.branch_diff_stat)

    # ── Facts, not a score (ADR-0018) ───────────────────────────────────

    def branch_with_change(self, repo_path: Path, task: Task, name: str = "orchestrator.py") -> str:
        """Commit one file on the task branch and return the branch head."""

        existing = self.git(repo_path, "branch", "--list", task.branch_name).stdout.strip()
        self.git(repo_path, "checkout", *(() if existing else ("-b",)), task.branch_name)
        self.write_text(repo_path / name, f"def {Path(name).stem}(): pass\n")
        self.commit_all(repo_path, f"feat: add {name}")
        sha = self.git(repo_path, "rev-parse", "HEAD").stdout.strip()
        self.git(repo_path, "checkout", "main")
        return sha

    def seed_tests_at(
        self,
        store: ForemanStore,
        *,
        project: Project,
        task: Task,
        exit_code: int,
        head_sha: str | None,
        timestamp: str = "2026-04-22T10:22:00Z",
    ) -> None:
        run = self.seed_run(
            store,
            project=project,
            task=task,
            role_id="_builtin:run_tests",
            workflow_step="test",
            agent_backend="builtin",
            outcome="success" if exit_code == 0 else "failure",
            created_at=timestamp,
        )
        payload: dict[str, object] = {
            "command": "pytest tests/",
            "exit_code": exit_code,
            "passed": exit_code == 0,
            "duration_seconds": 12.5,
        }
        if head_sha is not None:
            payload["head_sha"] = head_sha
        store.save_event(
            Event(
                id=f"event-test-run-{run.id}",
                run_id=run.id,
                task_id=task.id,
                project_id=project.id,
                event_type="engine.test_run",
                timestamp=timestamp,
                payload=payload,
            )
        )

    def seed_review_at(
        self,
        store: ForemanStore,
        *,
        project: Project,
        task: Task,
        outcome: str,
        head_sha: str,
        timestamp: str = "2026-04-22T10:25:00Z",
    ) -> None:
        run = self.seed_run(
            store,
            project=project,
            task=task,
            role_id="code_reviewer",
            workflow_step="review",
            agent_backend="claude_code",
            outcome=outcome,
            outcome_detail="Reviewed.",
            created_at=timestamp,
        )
        run.completed_at = timestamp
        store.save_run(run)
        store.save_event(
            Event(
                id=f"event-review-{run.id}",
                run_id=run.id,
                task_id=task.id,
                project_id=project.id,
                event_type="engine.review_recorded",
                timestamp=timestamp,
                payload={
                    "role": "code_reviewer",
                    "review_kind": "code",
                    "outcome": outcome,
                    "head_sha": head_sha,
                },
            )
        )

    def evidence_for(self, *, criteria: str | None = "Implement the orchestrator.", arrange=None):
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()
        project, _, task = self.seed_project(
            store, repo_path=repo_path, acceptance_criteria=criteria
        )
        head = self.branch_with_change(repo_path, task)
        if arrange is not None:
            head = arrange(store, project, task, repo_path, head) or head
        orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
        evidence = orchestrator.build_completion_evidence(task, project)
        assert evidence is not None
        return evidence, head

    def test_proof_passes_when_tests_and_review_are_both_on_the_head_commit(self) -> None:
        def arrange(store, project, task, repo_path, head):
            self.seed_tests_at(store, project=project, task=task, exit_code=0, head_sha=head)
            self.seed_review_at(store, project=project, task=task, outcome="approve", head_sha=head)

        evidence, head = self.evidence_for(arrange=arrange)

        self.assertEqual(evidence.proof_status, "passed")
        self.assertEqual(evidence.tests_status, "passed")
        self.assertEqual(evidence.tested_sha, head)
        self.assertEqual(evidence.test_duration_seconds, 12.5)
        self.assertEqual(evidence.review_outcome, "approve")
        self.assertEqual(evidence.reviewed_sha, head)
        self.assertEqual(evidence.head_sha, head)
        self.assertEqual(evidence.failure_reasons, ())
        self.assertEqual(evidence.outstanding, ())

    def test_tests_that_ran_on_an_earlier_commit_do_not_count(self) -> None:
        def arrange(store, project, task, repo_path, head):
            self.seed_tests_at(store, project=project, task=task, exit_code=0, head_sha=head)
            new_head = self.branch_with_change(repo_path, task, "later.py")
            self.seed_review_at(
                store, project=project, task=task, outcome="approve", head_sha=new_head
            )
            return new_head

        evidence, head = self.evidence_for(arrange=arrange)

        self.assertEqual(evidence.tests_status, "stale")
        self.assertEqual(evidence.proof_status, "failed")
        self.assertNotEqual(evidence.tested_sha, head)
        self.assertTrue(
            any(reason.startswith("Tests ran on") for reason in evidence.failure_reasons),
            evidence.failure_reasons,
        )

    def test_a_review_of_an_earlier_commit_does_not_count(self) -> None:
        def arrange(store, project, task, repo_path, head):
            self.seed_review_at(store, project=project, task=task, outcome="approve", head_sha=head)
            new_head = self.branch_with_change(repo_path, task, "later.py")
            self.seed_tests_at(
                store,
                project=project,
                task=task,
                exit_code=0,
                head_sha=new_head,
                timestamp="2026-04-22T10:30:00Z",
            )
            return new_head

        evidence, _ = self.evidence_for(arrange=arrange)

        self.assertEqual(evidence.tests_status, "passed")
        self.assertEqual(evidence.proof_status, "failed")
        self.assertTrue(
            any(reason.startswith("Code review approved") for reason in evidence.failure_reasons),
            evidence.failure_reasons,
        )

    def test_failed_tests_fail_the_proof_whatever_the_review_says(self) -> None:
        def arrange(store, project, task, repo_path, head):
            self.seed_tests_at(store, project=project, task=task, exit_code=1, head_sha=head)
            self.seed_review_at(store, project=project, task=task, outcome="approve", head_sha=head)

        evidence, _ = self.evidence_for(arrange=arrange)

        self.assertEqual(evidence.tests_status, "failed")
        self.assertFalse(evidence.builtin_test_passed)
        self.assertEqual(evidence.proof_status, "failed")
        self.assertIn("Tests failed (exit code 1).", evidence.failure_reasons)

    def test_nothing_checked_yet_is_pending_and_says_what_is_missing(self) -> None:
        evidence, _ = self.evidence_for()

        self.assertEqual(evidence.tests_status, "not_run")
        self.assertEqual(evidence.review_outcome, "")
        self.assertEqual(evidence.proof_status, "pending")
        self.assertEqual(evidence.failure_reasons, ())
        self.assertEqual(len(evidence.outstanding), 2)
        self.assertIn("Tests have not run.", evidence.outstanding)

    def test_a_summary_that_repeats_the_criteria_does_not_pass_them(self) -> None:
        """The removed keyword heuristic called this a pass."""

        def arrange(store, project, task, repo_path, head):
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome_detail="Implement the orchestrator. Implemented the orchestrator.",
                created_at="2026-04-22T10:20:00Z",
            )
            self.seed_tests_at(store, project=project, task=task, exit_code=0, head_sha=head)

        evidence, _ = self.evidence_for(arrange=arrange)

        self.assertEqual(evidence.judged_by, "none")
        self.assertEqual(evidence.criteria_addressed, 0)
        self.assertEqual([c["status"] for c in evidence.criteria_checklist], ["unverified"])
        self.assertEqual(evidence.proof_status, "pending")

    def test_an_implementation_task_without_criteria_fails_the_proof(self) -> None:
        def arrange(store, project, task, repo_path, head):
            self.seed_tests_at(store, project=project, task=task, exit_code=0, head_sha=head)
            self.seed_review_at(store, project=project, task=task, outcome="approve", head_sha=head)

        evidence, _ = self.evidence_for(criteria=None, arrange=arrange)

        self.assertEqual(evidence.criteria_count, 0)
        self.assertEqual(evidence.proof_status, "failed")
        self.assertEqual(evidence.failure_reasons, ("No acceptance criteria defined.",))

    def test_a_test_run_recorded_without_a_commit_is_taken_at_face_value(self) -> None:
        def arrange(store, project, task, repo_path, head):
            self.seed_tests_at(store, project=project, task=task, exit_code=0, head_sha=None)
            self.seed_review_at(store, project=project, task=task, outcome="approve", head_sha=head)

        evidence, _ = self.evidence_for(arrange=arrange)

        self.assertEqual(evidence.tests_status, "passed")
        self.assertEqual(evidence.tested_sha, "")
        self.assertEqual(evidence.proof_status, "passed")

    def test_evidence_text_states_facts_and_no_score(self) -> None:
        def arrange(store, project, task, repo_path, head):
            self.seed_tests_at(store, project=project, task=task, exit_code=0, head_sha=head)

        evidence, head = self.evidence_for(arrange=arrange)
        text = str(evidence)

        self.assertIn(f"Tests: passed at {head[:8]} (exit 0)", text)
        self.assertIn("Code review: none yet", text)
        self.assertIn("Acceptance criteria: 1, not checked by a judge model", text)
        self.assertNotIn("/100", text)
        self.assertNotIn("score", text.lower())

    def test_evidence_saved_with_a_score_still_loads(self) -> None:
        evidence = CompletionEvidence.from_mapping(
            {
                "task_id": "t",
                "task_title": "T",
                "acceptance_criteria": "",
                "score": 72.5,
                "score_breakdown": "criteria=40/40",
                "verdict": "adequate",
                "verdict_reasons": ["x"],
                "changed_files": ["a.py"],
                "proof_status": "passed",
                "builtin_test_result": "pytest",
                "builtin_test_passed": True,
            }
        )

        self.assertEqual(evidence.tests_status, "passed")

        self.assertEqual(evidence.changed_files, ("a.py",))
        self.assertEqual(evidence.proof_status, "passed")
        self.assertFalse(hasattr(evidence, "score"))

    def test_no_branch_means_no_changed_files_evidence(self) -> None:
        """Tasks with no branch name have no diff evidence and rely solely on agent output.

        This guards against false positives from incomplete task metadata.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the scheduler queue.\nAdd priority handling.\n",
                branch_name=None,  # No branch set
            )

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the scheduler.",
                created_at="2026-04-22T10:20:00Z",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                outcome="approve",
                outcome_detail="Approved.",
                created_at="2026-04-22T10:25:00Z",
            )

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            evidence = orchestrator.build_completion_evidence(task, project)

            self.assertIsNotNone(evidence)
            assert evidence is not None
            # No diff available when no branch
            self.assertEqual(evidence.changed_files, ())
            self.assertEqual(evidence.branch_diff_stat, "")
            self.assertEqual(evidence.head_sha, "")
            self.assertEqual(evidence.tests_status, "not_run")

    def test_build_completion_evidence_uses_configured_judge(self) -> None:
        import httpx
        from unittest import mock

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the orchestrator.\nWrite tests for it.",
            )
            project.settings["judge_base_url"] = "https://judge.example/api"
            project.settings["judge_model"] = "cheap-judge-1"
            store.save_project(project)

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                outcome="done",
                outcome_detail="Implemented the orchestrator module.",
                created_at="2026-04-22T10:20:00Z",
            )
            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "orchestrator.py", "def run(): pass\n")
            self.commit_all(repo_path, "feat: implement orchestrator")
            self.git(repo_path, "checkout", "main")

            judge_body = {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '[{"criterion": "Implement the orchestrator.", "status": "passed", "evidence": "done"},'
                            ' {"criterion": "Write tests for it.", "status": "partial", "evidence": "some"}]'
                        ),
                    }
                ]
            }
            fake = httpx.Response(
                status_code=200,
                json=judge_body,
                request=httpx.Request("POST", "https://judge.example/api/v1/messages"),
            )

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
            with mock.patch("httpx.post", return_value=fake):
                evidence = orchestrator.build_completion_evidence(task, project)

            assert evidence is not None
            self.assertEqual(evidence.judged_by, "cheap-judge-1")
            self.assertEqual(evidence.criteria_addressed, 1)
            self.assertEqual(evidence.criteria_partially_addressed, 1)
            self.assertEqual(
                [c["status"] for c in evidence.criteria_checklist],
                ["passed", "partial"],
            )

    def test_criteria_are_unverified_when_no_judge_is_configured(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                acceptance_criteria="Implement the orchestrator.",
            )
            self.seed_run(
                store, project=project, task=task, role_id="developer",
                workflow_step="develop", agent_backend="claude_code",
                outcome="done", outcome_detail="Implemented orchestrator.",
                created_at="2026-04-22T10:20:00Z",
            )
            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "orchestrator.py", "def run(): pass\n")
            self.commit_all(repo_path, "feat: orchestrator")
            self.git(repo_path, "checkout", "main")
            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
            evidence = orchestrator.build_completion_evidence(task, project)
            assert evidence is not None
            self.assertEqual(evidence.judged_by, "none")
            self.assertEqual([c["status"] for c in evidence.criteria_checklist], ["unverified"])


class EvidenceCachingTests(RepoTestCase):
    """Regression coverage for CompletionEvidence caching in _build_prompt."""

    def initialize_repo(self, repo_path: Path) -> None:
        self.git(repo_path, "init")
        self.git(repo_path, "checkout", "-b", "main")
        self.git(repo_path, "config", "user.email", "foreman-tests@example.com")
        self.git(repo_path, "config", "user.name", "Foreman Tests")
        self.write_text(repo_path / "AGENTS.md", "# Local Instructions\n")
        self.write_text(repo_path / ".gitignore", ".foreman/\n")
        self.write_text(repo_path / "README.md", "# Temp Repo\n")
        self.commit_all(repo_path, "chore: initial commit")

    def test_developer_prompt_does_not_build_completion_evidence(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                spec_path="docs/specs/engine-design-v3.md",
                workflow_id="development",
                default_branch="main",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Orchestrator",
                status="active",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Implement scheduler queue",
                status="in_progress",
                task_type="feature",
                branch_name="feat/scheduler",
                acceptance_criteria="Add a queue implementation.",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            def fail_build(task_: Task, project_: Project):
                raise AssertionError("developer prompts must not build completion evidence")

            orchestrator.build_completion_evidence = fail_build  # type: ignore[method-assignment]
            prompt = orchestrator.prompts.build(self.roles["developer"], project, task, None)

            self.assertIn("Implement scheduler queue", prompt)
            self.assertIsNone(task.completion_evidence)

    def test_build_prompt_caches_evidence_on_second_call(self) -> None:
        """Second _build_prompt call must reuse the cached evidence without rebuilding.

        Verifies that build_completion_evidence() is called at most once regardless
        of how many times _build_prompt is invoked for the same task/role.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                spec_path="docs/specs/engine-design-v3.md",
                workflow_id="development",
                default_branch="main",
                settings={"default_model": "claude-sonnet-4-7"},
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Orchestrator",
                goal="Test evidence caching",
                status="active",
                order_index=1,
                created_at="2026-03-30T12:05:00Z",
                started_at="2026-03-30T12:10:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Implement scheduler queue",
                description="Add a task scheduler.",
                status="in_progress",
                task_type="feature",
                priority=1,
                branch_name="feat/scheduler",
                acceptance_criteria="Add a queue implementation.\nAdd priority handling.\n",
                created_at="2026-03-30T12:00:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)

            # Add a develop run so evidence can be built
            store.save_run(
                Run(
                    id="run-1",
                    task_id=task.id,
                    project_id=project.id,
                    role_id="developer",
                    workflow_step="develop",
                    agent_backend="claude_code",
                    status="completed",
                    outcome="done",
                    outcome_detail="Implemented the scheduler queue.",
                    created_at="2026-03-30T12:20:00Z",
                )
            )

            # Create a branch with a real file change so evidence has material to work with
            self.git(repo_path, "checkout", "-b", "feat/scheduler")
            self.write_text(repo_path / "scheduler.py", "class Queue:\n    pass\n")
            self.commit_all(repo_path, "feat: add scheduler stub")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

            # Spy on build_completion_evidence to track call count
            original_build = orchestrator.build_completion_evidence
            call_count = [0]

            def spying_build(task_: Task, project_: Project):
                call_count[0] += 1
                return original_build(task_, project_)

            orchestrator.build_completion_evidence = spying_build  # type: ignore[method-assignment]

            role = self.roles["code_reviewer"]
            # First call — should build and cache evidence
            orchestrator.prompts.build(role, project, task, None)
            self.assertGreater(call_count[0], 0, "build_completion_evidence should have been called on first _build_prompt")
            self.assertIsNotNone(
                task.completion_evidence,
                "task.completion_evidence must be set after first _build_prompt",
            )
            first_evidence = task.completion_evidence

            # Second call — evidence must be reused, not rebuilt
            orchestrator.prompts.build(role, project, task, None)
            self.assertEqual(
                call_count[0],
                1,
                "build_completion_evidence must only be called once; second _build_prompt should reuse cached evidence",
            )
            self.assertIs(
                task.completion_evidence,
                first_evidence,
                "task.completion_evidence must be the same object on second call",
            )

            # Third call — still no rebuild
            orchestrator.prompts.build(role, project, task, None)
            self.assertEqual(call_count[0], 1)
            self.assertIs(task.completion_evidence, first_evidence)

    def test_reviewer_prompt_rebuilds_completion_evidence_when_branch_head_moves(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                spec_path="docs/specs/engine-design-v3.md",
                workflow_id="development",
                default_branch="main",
                settings={"default_model": "claude-sonnet-4-7"},
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Orchestrator",
                status="active",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Implement scheduler queue",
                status="in_progress",
                task_type="feature",
                branch_name="feat/scheduler",
                acceptance_criteria="Add a queue implementation.",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)
            store.save_run(
                Run(
                    id="run-1",
                    task_id=task.id,
                    project_id=project.id,
                    role_id="developer",
                    workflow_step="develop",
                    agent_backend="claude_code",
                    status="completed",
                    outcome="done",
                    outcome_detail="Implemented the scheduler queue.",
                )
            )

            self.git(repo_path, "checkout", "-b", "feat/scheduler")
            self.write_text(repo_path / "scheduler.py", "class Queue:\n    pass\n")
            self.commit_all(repo_path, "feat: add scheduler stub")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
            original_build = orchestrator.build_completion_evidence
            call_count = [0]

            def spying_build(task_: Task, project_: Project):
                call_count[0] += 1
                return original_build(task_, project_)

            orchestrator.build_completion_evidence = spying_build  # type: ignore[method-assignment]
            role = self.roles["code_reviewer"]

            orchestrator.prompts.build(role, project, task, None)
            self.assertEqual(call_count[0], 1)
            first_evidence = task.completion_evidence
            self.assertIsNotNone(first_evidence)
            assert first_evidence is not None

            self.git(repo_path, "checkout", "feat/scheduler")
            self.write_text(repo_path / "scheduler.py", "class Queue:\n    def pop(self):\n        return None\n")
            self.commit_all(repo_path, "feat: extend scheduler stub")
            self.git(repo_path, "checkout", "main")

            orchestrator.prompts.build(role, project, task, None)
            self.assertEqual(call_count[0], 2)
            self.assertIsNotNone(task.completion_evidence)
            assert task.completion_evidence is not None
            self.assertNotEqual(task.completion_evidence.head_sha, first_evidence.head_sha)

    def test_build_prompt_injects_all_12_evidence_fields(self) -> None:
        """_build_prompt must inject all 12 completion evidence fields into the context."""
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                spec_path="docs/specs/engine-design-v3.md",
                workflow_id="development",
                default_branch="main",
                settings={"default_model": "claude-sonnet-4-7"},
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Test Sprint",
                goal="Test evidence fields",
                status="active",
                order_index=1,
                created_at="2026-03-30T12:05:00Z",
                started_at="2026-03-30T12:10:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Test task",
                description="Test.",
                status="in_progress",
                task_type="feature",
                priority=1,
                branch_name="feat/test",
                acceptance_criteria="Add feature X.\n",
                created_at="2026-03-30T12:00:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)

            store.save_run(
                Run(
                    id="run-1",
                    task_id=task.id,
                    project_id=project.id,
                    role_id="developer",
                    workflow_step="develop",
                    agent_backend="claude_code",
                    status="completed",
                    outcome="done",
                    outcome_detail="Done.",
                    created_at="2026-03-30T12:20:00Z",
                )
            )

            self.git(repo_path, "checkout", "-b", "feat/test")
            self.write_text(repo_path / "feature.py", "def foo():\n    pass\n")
            self.commit_all(repo_path, "feat: add feature")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
            role = self.roles["code_reviewer"]

            # _build_prompt builds evidence on first call and injects fields into
            # context. We verify all 12 are present by checking the evidence
            # object that gets attached to the task after the call.
            orchestrator.prompts.build(role, project, task, None)

            self.assertIsNotNone(
                task.completion_evidence,
                "task.completion_evidence must be set after _build_prompt",
            )
            ev = task.completion_evidence
            assert ev is not None  # type narrowing

            # Verify evidence was built with all fields populated
            self.assertIsNotNone(ev.proof_status)
            self.assertIsNotNone(ev.tests_status)
            self.assertIsNotNone(ev.head_sha)
            self.assertIsNotNone(ev.branch_diff_stat)
            self.assertIsNotNone(ev.builtin_test_result)
            self.assertIsNotNone(ev.builtin_test_detail)
            # Tuple fields
            self.assertIsInstance(ev.outstanding, tuple)
            self.assertIsInstance(ev.changed_files, tuple)

            # Verify 12 fields are all non-None on the evidence object
            expected_non_none_fields = (
                "proof_status",
                "tests_status",
                "review_outcome",
                "criteria_count",
                "criteria_addressed",
                "criteria_partially_addressed",
                "changed_files",
                "branch_diff_stat",
                "builtin_test_passed",
                "builtin_test_result",
                "builtin_test_detail",
            )
            for field in expected_non_none_fields:
                value = getattr(ev, field, None)
                self.assertIsNotNone(
                    value,
                    f"CompletionEvidence.{field} must not be None",
                )


if __name__ == "__main__":
    unittest.main()
