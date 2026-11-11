"""Running a role: backends, sessions, retries, heartbeats."""

from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import unittest
from foreman.models import Task
from foreman.engine.results import AgentExecutionResult
from foreman.orchestrator import ForemanOrchestrator
from foreman.git import current_branch
from foreman.runner.base import AgentEvent, AgentRunConfig, InfrastructureError, PreflightError
from foreman.store import ForemanStore

from engine_support import (
    OrchestratorTestCase,
    ScriptedAgentExecutor,
    ScriptedNativeRunner,
    _LongStreamingRunner,
)


class AgentStepTests(OrchestratorTestCase):
    """Running a role: backends, sessions, retries, heartbeats."""

    def test_run_project_retries_developer_once_after_missing_completion_marker(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)

            def developer_missing_marker(
                *,
                task: Task,
                prompt: str,
                carried_output: str | None,
            ) -> AgentExecutionResult:
                self.assertIn("Task: Implement orchestrator loop", prompt)
                return AgentExecutionResult(
                    outcome="error",
                    detail="Missing completion marker `TASK_COMPLETE`.",
                    status="completed",
                )

            def developer_retry(
                *,
                task: Task,
                prompt: str,
                carried_output: str | None,
            ) -> AgentExecutionResult:
                self.assertIn("### Output Correction", prompt)
                self.assertIn("end with `TASK_COMPLETE`", prompt)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "implemented\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement workflow slice")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the workflow slice.",
                    status="completed",
                )

            executor = ScriptedAgentExecutor(
                {
                    ("developer", 1): developer_missing_marker,
                    ("developer", 2): developer_retry,
                    ("code_reviewer", 1): lambda **_: AgentExecutionResult(
                        outcome="approve",
                        detail="APPROVE",
                    ),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(executor.call_counts["developer"], 2)
            final_task = store.get_task(task.id)
            assert final_task is not None
            self.assertEqual(final_task.status, "done")
            retry_events = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "engine.output_contract_retry"
            ]
            self.assertEqual(len(retry_events), 1)
            self.assertEqual(retry_events[0].payload["reason"], "missing_completion_marker")

    def test_run_project_retries_reviewer_once_after_malformed_decision_output(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)

            def developer_success(
                *,
                task: Task,
                prompt: str,
                carried_output: str | None,
            ) -> AgentExecutionResult:
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "implemented\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement workflow slice")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the workflow slice.",
                    status="completed",
                )

            def malformed_review(
                *,
                task: Task,
                prompt: str,
                carried_output: str | None,
            ) -> AgentExecutionResult:
                self.assertIn("Developer Summary", prompt)
                return AgentExecutionResult(
                    outcome="error",
                    detail="<invoke name=\"Bash\">bad tool call</invoke>",
                    status="completed",
                )

            def corrected_review(
                *,
                task: Task,
                prompt: str,
                carried_output: str | None,
            ) -> AgentExecutionResult:
                self.assertIn("### Output Correction", prompt)
                self.assertIn("Return exactly one line and nothing else", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="APPROVE",
                    status="completed",
                )

            executor = ScriptedAgentExecutor(
                {
                    ("developer", 1): developer_success,
                    ("code_reviewer", 1): malformed_review,
                    ("code_reviewer", 2): corrected_review,
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(executor.call_counts["code_reviewer"], 2)
            final_task = store.get_task(task.id)
            assert final_task is not None
            self.assertEqual(final_task.status, "done")
            retry_events = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "engine.output_contract_retry"
            ]
            self.assertEqual(len(retry_events), 1)
            self.assertEqual(retry_events[0].payload["reason"], "decision_format")

    def test_native_runner_executes_claude_roles_without_an_injected_executor(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            store.save_project(project)
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(config),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "idle")
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

            developer_capture = runner.capture(1)
            reviewer_capture = runner.capture(2)
            self.assertEqual(developer_capture.model, "claude-sonnet-4-6")
            self.assertIsNone(developer_capture.session_id)
            self.assertEqual(reviewer_capture.disallowed_tools, ("Bash", "Write", "Edit", "NotebookEdit"))

            runs = store.list_runs(task_id=task.id)
            workflow_runs = [r for r in runs if r.role_id != "_builtin:orchestrator"]
            self.assertEqual(
                [run.workflow_step for run in workflow_runs],
                ["develop", "test", "review", "merge_approval", "merge", "done"],
            )
            self.assertEqual(workflow_runs[0].session_id, "dev-session")
            self.assertEqual(
                [run.outcome for run in workflow_runs],
                ["done", "success", "approve", "approve", "success", "success"],
            )

    def test_native_runner_records_retry_count_from_infra_errors(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            store.save_project(project)
            # Call 1 aborts with an InfrastructureError (run_with_retry replays),
            # call 2 is the developer success, call 3 is the reviewer approval.
            runner = ScriptedNativeRunner(
                {
                    1: InfrastructureError("transient backend failure"),
                    2: lambda config: self._native_developer_success(config),
                    3: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
                runner_sleep=lambda _seconds: None,
            )

            result = orchestrator.run_project(project.id)
            self.assertEqual(result.executed_task_ids, (task.id,))

            develop_run = next(
                r for r in store.list_runs(task_id=task.id) if r.workflow_step == "develop"
            )
            self.assertEqual(develop_run.retry_count, 1)
            # The retry replay also left an agent.infra_error in the transcript.
            infra_events = [
                e for e in store.list_events(task_id=task.id)
                if e.event_type == "agent.infra_error"
            ]
            self.assertEqual(len(infra_events), 1)

    def test_an_interrupted_attempt_is_resumed_and_its_cost_stays_on_the_run(self) -> None:
        from foreman.runner.base import RESUME_AFTER_INFRA_ERROR_PROMPT

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            store.save_project(project)

            def interrupted(config: AgentRunConfig):
                yield AgentEvent("agent.session", payload={"session_id": "dev-session"})
                yield AgentEvent(
                    "agent.cost_update", payload={"cumulative_usd": 0.5, "cumulative_tokens": 90}
                )
                raise InfrastructureError("stream ended without a terminal result event")

            def resumed(config: AgentRunConfig):
                work_dir = Path(config.working_dir)
                self.write_text(work_dir / "feature.txt", "implemented\n")
                self.write_text(work_dir / "ready.txt", "ready\n")
                self.commit_all(work_dir, "feat: finish after the interruption")
                yield AgentEvent(
                    "agent.message",
                    payload={"text": "Finished the slice.\nTASK_COMPLETE", "phase": "assistant"},
                )
                yield AgentEvent(
                    "agent.completed",
                    payload={"session_id": "dev-session", "cost_usd": 1.2, "token_count": 250},
                )

            runner = ScriptedNativeRunner(
                {
                    1: interrupted,
                    2: resumed,
                    3: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
                runner_sleep=lambda _seconds: None,
            )

            orchestrator.run_project(project.id)

            # The second attempt continued the session instead of replaying
            # the whole prompt into it.
            self.assertEqual(runner.captures[1].session_id, "dev-session")
            self.assertEqual(runner.captures[1].prompt, RESUME_AFTER_INFRA_ERROR_PROMPT)
            develop_run = next(
                r for r in store.list_runs(task_id=task.id) if r.workflow_step == "develop"
            )
            self.assertEqual(develop_run.retry_count, 1)
            self.assertAlmostEqual(develop_run.cost_usd, 1.7)
            self.assertEqual(develop_run.session_id, "dev-session")

    def test_native_runner_resolves_role_env_before_execution(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "minimax-m3"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            roles = {
                role_id: (
                    replace(
                        role,
                        agent=replace(
                            role.agent,
                            env={
                                "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
                                "ANTHROPIC_AUTH_TOKEN": "env:FOREMAN_TEST_MINIMAX_TOKEN?test-token",
                                "CLAUDE_CONFIG_DIR": "env:FOREMAN_TEST_MINIMAX_CONFIG_DIR?~/.foreman/claude-minimax-test",
                            },
                        ),
                    )
                    if role_id == "developer"
                    else role
                )
                for role_id, role in self.roles.items()
            }
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(config),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            capture = runner.capture(1)
            self.assertEqual(capture.model, "minimax-m3")
            self.assertEqual(capture.env["ANTHROPIC_BASE_URL"], "https://api.minimax.io/anthropic")
            self.assertEqual(capture.env["ANTHROPIC_AUTH_TOKEN"], "test-token")
            self.assertTrue(capture.env["CLAUDE_CONFIG_DIR"].endswith(".foreman/claude-minimax-test"))

    def test_missing_required_role_env_fails_once_without_runner_retry(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            store.save_project(project)
            roles = {
                role_id: (
                    replace(
                        role,
                        agent=replace(
                            role.agent,
                            env={"ANTHROPIC_AUTH_TOKEN": "env:FOREMAN_TEST_MISSING_MINIMAX_TOKEN"},
                        ),
                    )
                    if role_id == "developer"
                    else role
                )
                for role_id, role in self.roles.items()
            }
            runner = ScriptedNativeRunner({})
            orchestrator = ForemanOrchestrator(
                store,
                roles=roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.blocked_task_ids, (task.id,))
            self.assertEqual(runner.call_count, 0)
            error_events = [
                event for event in store.list_events(task_id=task.id)
                if event.event_type == "agent.error"
            ]
            self.assertEqual(len(error_events), 1)
            self.assertTrue(error_events[0].payload["preflight_failed"])
            self.assertIn("FOREMAN_TEST_MISSING_MINIMAX_TOKEN", error_events[0].payload["error"])

    def test_native_runner_reuses_persistent_developer_sessions_after_review_denial(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_initial_pass(config),
                    2: lambda config: self._native_reviewer_deny(config),
                    3: lambda config: self._native_developer_followup(config),
                    4: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(runner.capture(1).session_id, None)
            self.assertEqual(runner.capture(3).session_id, "dev-session")
            self.assertIn("Please add the ready marker.", runner.capture(3).prompt)

            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.step_visit_counts,
                {
                    "develop": 2,
                    "test": 2,
                    "review": 2,
                    "merge_approval": 1,
                    "merge": 1,
                    "done": 1,
                },
            )

    def test_native_runner_reuses_persisted_claude_session_after_fresh_orchestrator_invocation(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            task.status = "in_progress"
            task.workflow_current_step = "develop"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                session_id="persisted-dev-session",
                outcome_detail="Previous development run.",
                created_at="2026-03-30T12:21:00Z",
                model="claude-sonnet-4-6",
            )
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_resumed(
                        config,
                        expected_session_id="persisted-dev-session",
                    ),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = resume_orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(runner.capture(1).session_id, "persisted-dev-session")
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

    def test_non_persistent_native_roles_ignore_persisted_sessions_after_fresh_orchestrator_invocation(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            task.status = "in_progress"
            task.workflow_current_step = "review"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)

            self.git(repo_path, "checkout", "-b", task.branch_name)
            self.write_text(repo_path / "feature.txt", "implemented already\n")
            self.write_text(repo_path / "ready.txt", "ready\n")
            self.commit_all(repo_path, "feat: seed branch for review")
            self.git(repo_path, "checkout", "main")

            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                session_id="persisted-dev-session",
                outcome_detail="Developer finished work.",
                created_at="2026-03-30T12:21:00Z",
                model="claude-sonnet-4-6",
            )
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                session_id="stale-review-session",
                outcome="deny",
                outcome_detail="Previous review session.",
                created_at="2026-03-30T12:22:00Z",
                model="claude-sonnet-4-6",
            )

            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_reviewer_approve(config),
                }
            )
            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = resume_orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertIsNone(runner.capture(1).session_id)
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

    def test_native_runner_infra_retries_are_persisted_and_block_the_task_on_exhaustion(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                task_title="Handle runner outage",
            )
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["max_infra_retries"] = 2
            store.save_project(project)
            runner = ScriptedNativeRunner(
                {
                    1: InfrastructureError("claude unavailable"),
                    2: InfrastructureError("claude unavailable"),
                    3: InfrastructureError("claude unavailable"),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
                runner_sleep=lambda _: None,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "blocked")
            blocked_task = store.get_task(task.id)
            self.assertIsNotNone(blocked_task)
            assert blocked_task is not None
            self.assertEqual(blocked_task.status, "blocked")
            self.assertEqual(
                blocked_task.blocked_reason,
                "claude unavailable",
            )

            event_types = [event.event_type for event in store.list_events(task_id=task.id)]
            self.assertEqual(event_types.count("agent.infra_error"), 2)
            self.assertIn("agent.error", event_types)
            runs = store.list_runs(task_id=task.id)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "failed")
            self.assertEqual(runs[0].outcome, "error")

    def test_native_runner_preflight_failure_is_not_retried(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                task_title="Handle missing Claude executable",
            )
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["max_infra_retries"] = 2
            store.save_project(project)
            runner = ScriptedNativeRunner(
                {
                    1: PreflightError(
                        "Claude Code preflight failed: executable `claude` was not found in PATH."
                    ),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
                runner_sleep=lambda _: None,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "blocked")
            self.assertEqual(runner.call_count, 1)
            blocked_task = store.get_task(task.id)
            self.assertIsNotNone(blocked_task)
            assert blocked_task is not None
            self.assertEqual(blocked_task.status, "blocked")
            self.assertEqual(
                blocked_task.blocked_reason,
                "Claude Code preflight failed: executable `claude` was not found in PATH.",
            )

            events = store.list_events(task_id=task.id)
            self.assertNotIn("agent.infra_error", [event.event_type for event in events])
            error_events = [event for event in events if event.event_type == "agent.error"]
            self.assertEqual(len(error_events), 1)
            self.assertTrue(error_events[0].payload["preflight_failed"])
            self.assertIn("executable `claude` was not found in PATH", error_events[0].payload["error"])
            runs = store.list_runs(task_id=task.id)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "failed")
            self.assertEqual(runs[0].outcome, "error")
            self.assertIn("preflight failed", runs[0].outcome_detail.lower())
            self.assertEqual(current_branch(repo_path), "main")

    def test_native_runner_persists_active_step_before_execution(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            store.save_project(project)

            def developer_handler(config: AgentRunConfig):
                persisted_task = store.get_task(task.id)
                assert persisted_task is not None
                self.assertEqual(persisted_task.workflow_current_step, "develop")
                self.assertIsNone(config.session_id)
                yield from self._native_developer_success(config)

            runner = ScriptedNativeRunner(
                {
                    1: developer_handler,
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            updated_task = store.get_task(task.id)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

    def test_native_runner_streams_events_before_a_mid_step_crash(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            store.save_project(project)

            def crashing_reviewer(_config: AgentRunConfig):
                yield AgentEvent(
                    "agent.started",
                    payload={"phase": "review"},
                    timestamp="2026-03-30T12:25:00Z",
                )
                yield AgentEvent(
                    "agent.message",
                    payload={"text": "Review is underway.", "phase": "assistant"},
                    timestamp="2026-03-30T12:25:05Z",
                )
                raise RuntimeError("review runner crashed")

            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(config),
                    2: crashing_reviewer,
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "blocked")
            updated_task = store.get_task(task.id)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "blocked")
            self.assertEqual(updated_task.blocked_reason, "review runner crashed")

            runs = store.list_runs(task_id=task.id)
            review_run = next(run for run in runs if run.workflow_step == "review")
            self.assertEqual(review_run.status, "failed")
            self.assertEqual(review_run.outcome, "error")
            events = store.list_events(run_id=review_run.id)
            event_types = [event.event_type for event in events]
            self.assertGreaterEqual(event_types.count("engine.context_write"), 1)
            self.assertIn("workflow.step_started", event_types)
            self.assertIn("agent.started", event_types)
            self.assertIn("agent.message", event_types)
            self.assertIn("agent.error", event_types)
            self.assertIn("workflow.step_completed", event_types)
            self.assertIn("workflow.no_transition", event_types)
            self.assertLess(event_types.index("agent.started"), event_types.index("agent.error"))
            self.assertLess(event_types.index("agent.message"), event_types.index("agent.error"))

    def test_native_runner_uses_project_time_limit_for_timeout_seconds(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "claude-sonnet-4-6"
            project.settings["time_limit_per_run_minutes"] = 7
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(config),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(runner.capture(1).timeout_seconds, 420)
            self.assertEqual(runner.capture(2).timeout_seconds, 420)

    def test_native_runner_step_heartbeats_task_lease_during_long_stream(self) -> None:
        """A long-running native runner step must heartbeat the task lease
        so the lease does not expire mid-step.
        """
        import time as _time

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            store.save_project(project)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": _LongStreamingRunner()},
                native_step_heartbeat_seconds=0.001,  # renew on every event
            )
            token = orchestrator.leases.acquire(task, project)
            assert token is not None
            initial_lease = store.get_active_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
            )
            assert initial_lease is not None
            initial_heartbeat = initial_lease.heartbeat_at
            initial_expires = initial_lease.expires_at

            # Force a wall-clock advance so the renewal produces a strictly
            # later heartbeat timestamp. SQLite stores microsecond precision.
            _time.sleep(0.01)

            # The scripted runner yields many events, exercising the heartbeat
            # path. Use the developer role to drive a real native step.
            developer_role = self.roles["developer"]
            result = orchestrator.agent_steps.execute_native(
                role=developer_role,
                project=project,
                task=task,
                workflow_step="develop",
                prompt="do the work",
                session_id=None,
            )
            self.assertEqual(result.status, "completed")

            # The lease must have been heartbeated during the stream, so the
            # expires_at should be strictly later than the initial value.
            refreshed_lease = store.get_active_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
            )
            assert refreshed_lease is not None
            self.assertEqual(refreshed_lease.id, initial_lease.id)
            self.assertGreater(refreshed_lease.heartbeat_at, initial_heartbeat)
            self.assertGreater(refreshed_lease.expires_at, initial_expires)

    def test_native_runner_step_heartbeat_disabled_when_interval_zero(self) -> None:
        """Setting ``native_step_heartbeat_seconds=0`` disables the in-step
        heartbeat so the lease is renewed only after the step returns.
        """
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            store.save_project(project)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_runners={"claude_code": _LongStreamingRunner()},
                native_step_heartbeat_seconds=0.0,
            )
            token = orchestrator.leases.acquire(task, project)
            assert token is not None
            initial_lease = store.get_active_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
            )
            assert initial_lease is not None
            initial_heartbeat = initial_lease.heartbeat_at

            developer_role = self.roles["developer"]
            # Even with many events, the heartbeat must not have been bumped
            # because the interval is zero (disabled).
            orchestrator.agent_steps.execute_native(
                role=developer_role,
                project=project,
                task=task,
                workflow_step="develop",
                prompt="do the work",
                session_id=None,
            )

            refreshed_lease = store.get_active_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
            )
            assert refreshed_lease is not None
            self.assertEqual(refreshed_lease.heartbeat_at, initial_heartbeat)

    def test_native_runner_executes_codex_roles_without_an_injected_executor(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "gpt-5.4"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            codex_roles = self.roles_with_backend(
                "codex",
                role_models={
                    "architect": "o3",
                    "code_reviewer": "gpt-5.4",
                    "developer": "",
                    "security_reviewer": "gpt-5.4",
                },
            )
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(config),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=codex_roles,
                workflows=self.workflows,
                agent_runners={"codex": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "idle")
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(runner.capture(1).model, "gpt-5.4")
            self.assertEqual(
                runner.capture(2).disallowed_tools,
                ("Bash", "Write", "Edit", "NotebookEdit"),
            )

            runs = store.list_runs(task_id=task.id)
            self.assertEqual(
                [run.workflow_step for run in runs if run.role_id != "_builtin:orchestrator"],
                ["develop", "test", "review", "merge_approval", "merge", "done"],
            )
            self.assertEqual(runs[0].agent_backend, "codex")
            self.assertEqual(
                next(r for r in runs if r.workflow_step == "review").agent_backend, "codex"
            )
            self.assertEqual(runs[0].session_id, "dev-session")

    def test_native_runner_reuses_persistent_codex_sessions_after_review_denial(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "gpt-5.4"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            codex_roles = self.roles_with_backend(
                "codex",
                role_models={
                    "architect": "o3",
                    "code_reviewer": "gpt-5.4",
                    "developer": "",
                    "security_reviewer": "gpt-5.4",
                },
            )
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_initial_pass(config),
                    2: lambda config: self._native_reviewer_deny(config),
                    3: lambda config: self._native_developer_followup(config),
                    4: lambda config: self._native_reviewer_approve(config),
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=codex_roles,
                workflows=self.workflows,
                agent_runners={"codex": runner},
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(runner.capture(1).session_id, None)
            self.assertEqual(runner.capture(3).session_id, "dev-session")
            self.assertIn("Please add the ready marker.", runner.capture(3).prompt)
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

    def test_native_runner_reuses_persisted_codex_session_after_fresh_orchestrator_invocation(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["default_model"] = "gpt-5.4"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            task.status = "in_progress"
            task.workflow_current_step = "develop"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            self.seed_run(
                store,
                project=project,
                task=task,
                role_id="developer",
                workflow_step="develop",
                agent_backend="codex",
                session_id="persisted-thread-123",
                outcome_detail="Previous codex run.",
                created_at="2026-03-30T12:21:00Z",
                model="gpt-5.4",
            )
            codex_roles = self.roles_with_backend(
                "codex",
                role_models={
                    "architect": "o3",
                    "code_reviewer": "gpt-5.4",
                    "developer": "",
                    "security_reviewer": "gpt-5.4",
                },
            )
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_resumed(
                        config,
                        expected_session_id="persisted-thread-123",
                    ),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=codex_roles,
                workflows=self.workflows,
                agent_runners={"codex": runner},
            )

            result = resume_orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            self.assertEqual(runner.capture(1).session_id, "persisted-thread-123")
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")

    def test_native_runner_executes_codex_resume_after_human_gate_approval(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_with_architect",
            )
            project.settings["default_model"] = "gpt-5.4"
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            blocked_task = Task(
                id=task.id,
                sprint_id=task.sprint_id,
                project_id=task.project_id,
                title=task.title,
                description=task.description,
                status="blocked",
                task_type=task.task_type,
                priority=task.priority,
                order_index=task.order_index,
                branch_name="feat/task-1-implement-orchestrator-loop",
                acceptance_criteria=task.acceptance_criteria,
                blocked_reason="Awaiting human approval",
                workflow_current_step="human_approval",
                created_at=task.created_at,
                started_at="2026-03-30T12:20:00Z",
            )
            store.save_task(blocked_task)
            codex_roles = self.roles_with_backend(
                "codex",
                role_models={
                    "architect": "o3",
                    "code_reviewer": "gpt-5.4",
                    "developer": "",
                    "security_reviewer": "gpt-5.4",
                },
            )
            runner = ScriptedNativeRunner(
                {
                    1: lambda config: self._native_developer_success(config),
                    2: lambda config: self._native_reviewer_approve(config),
                }
            )
            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=codex_roles,
                workflows=self.workflows,
                agent_runners={"codex": runner},
            )

            resume_result = resume_orchestrator.resume_human_gate(task.id, outcome="approve")

            self.assertFalse(resume_result.deferred)
            self.assertEqual(resume_result.next_step, "develop")
            self.assertEqual(resume_result.task.status, "done")
            self.assertEqual(runner.capture(1).model, "gpt-5.4")
            runs = store.list_runs(task_id=task.id)
            self.assertEqual(
                [run.workflow_step for run in runs if run.role_id != "_builtin:orchestrator"],
                ["human_approval", "develop", "test", "review", "merge_approval", "merge", "done"],
            )
            self.assertEqual(
                next(r for r in runs if r.workflow_step == "review").agent_backend, "codex"
            )


if __name__ == "__main__":
    unittest.main()
