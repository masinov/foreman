"""A task goes through the shipped workflows, step by step."""

from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from foreman.models import Event, Run, Sprint, Task
from foreman.engine.results import AgentExecutionResult
from foreman.orchestrator import ForemanOrchestrator
from foreman.git import current_branch
from foreman.store import ForemanStore
from foreman.workflows import (
    WorkflowDefinition,
    WorkflowFallback,
    WorkflowStep,
    WorkflowTransition,
)

from engine_support import (
    OrchestratorTestCase,
    ScriptedAgentExecutor,
)


class WorkflowExecutionTests(OrchestratorTestCase):
    """A task goes through the shipped workflows, step by step."""

    def test_run_project_advances_one_task_through_the_shipped_workflow(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            left_commits: list[str] = []

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("Task: Implement orchestrator loop", prompt)
                self.assertIn("Branch: feat/task-1", prompt)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "implemented\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement workflow slice")
                left_commits.append(
                    self.git(self.work_dir(task, repo_path), "rev-parse", "HEAD").stdout.strip()
                )
                return AgentExecutionResult(
                    outcome="done",
                    detail=(
                        "Implemented the workflow slice so the task reaches done "
                        "after review, test, and merge."
                    ),
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Implemented the workflow slice", prompt)
                self.assertIn("feature.txt", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after review.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                    }
                ),
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.blocked_task_ids, ())

            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.branch_name,
                "feat/task-1",
            )
            self.assertIsNotNone(updated_task.completed_at)
            self.assertEqual(current_branch(repo_path), "main")

            runs = store.list_runs(task_id=task.id)
            agent_runs = [r for r in runs if r.role_id != "_builtin:orchestrator"]
            self.assertEqual(
                [r.workflow_step for r in agent_runs],
                ["develop", "test", "review", "merge_approval", "merge", "done"],
            )
            self.assertEqual(
                [r.outcome for r in agent_runs],
                ["done", "success", "approve", "approve", "success", "success"],
            )
            # An agent run records the commit it left on the task branch.
            develop_run = next(r for r in agent_runs if r.workflow_step == "develop")
            self.assertEqual(develop_run.commit_sha, left_commits[0])
            # System runs have no agent to credit with a commit.
            self.assertTrue(all(
                r.commit_sha is None for r in runs if r.role_id == "_builtin:orchestrator"
            ))

            event_types = [event.event_type for event in store.list_events(task_id=task.id)]
            self.assertIn("engine.test_run", event_types)
            self.assertIn("engine.merge", event_types)
            self.assertIn("workflow.transition", event_types)
            self.assertNotIn("workflow.no_transition", event_types)

        # The work landed on the default branch, and the operator's checkout
        # was never touched to get it there: it is still on `main`, and its
        # working tree still holds only what it held before the run.
        merged = self.git(repo_path, "ls-tree", "-r", "--name-only", "main").stdout
        self.assertIn("feature.txt", merged)
        self.assertIn("ready.txt", merged)
        self.assertEqual(
            self.git(repo_path, "branch", "--show-current").stdout.strip(),
            "main",
        )
        self.assertFalse((repo_path / "feature.txt").is_file())

    def test_secure_workflow_runs_through_security_review_and_finishes_task(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_secure",
                task_title="Ship secure workflow slice",
            )
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("Task: Ship secure workflow slice", prompt)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "secure implementation\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement secure workflow slice")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the secure workflow slice.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Implemented the secure workflow slice.", prompt)
                self.assertIn("feature.txt", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved for security review.",
                )

            def security_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Inspect the code changes on branch", prompt)
                self.assertIn("feature.txt", prompt)
                self.assertIn("ready.txt", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="No security issues found.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                        ("security_reviewer", 1): security_handler,
                    }
                ),
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.blocked_task_ids, ())
            self.assertEqual(result.stop_reason, "idle")

            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.step_visit_counts,
                {
                    "develop": 1,
                    "test": 1,
                    "code_review": 1,
                    "security_review": 1,
                    "merge_approval": 1,
                    "merge": 1,
                    "done": 1,
                },
            )

            runs = store.list_runs(task_id=task.id)
            agent_runs = [r for r in runs if r.role_id != "_builtin:orchestrator"]
            self.assertEqual(
                [r.workflow_step for r in agent_runs],
                ["develop", "test", "code_review", "security_review", "merge_approval", "merge", "done"],
            )
            self.assertEqual(
                [r.outcome for r in agent_runs],
                ["done", "success", "approve", "approve", "approve", "success", "success"],
            )

            transitions = [
                event.payload
                for event in store.list_events(task_id=task.id)
                if event.event_type == "workflow.transition"
            ]
            self.assertIn(
                {
                    "from_step": "code_review",
                    "to_step": "security_review",
                    "trigger": "completion:approve",
                },
                transitions,
            )
            self.assertIn(
                {
                    "from_step": "security_review",
                    "to_step": "merge_approval",
                    "trigger": "completion:approve",
                },
                transitions,
            )

    def test_security_review_denial_carries_output_back_into_development(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_secure",
                task_title="Remove insecure token handling",
            )
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            executor = ScriptedAgentExecutor({})

            def developer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "token = 'hardcoded'\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: initial secure workflow implementation")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Initial implementation complete.",
                )

            def reviewer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Initial implementation complete.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved for security review.",
                )

            def security_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("feature.txt", prompt)
                return AgentExecutionResult(
                    outcome="deny",
                    detail="Remove the hardcoded token in feature.txt.",
                )

            def developer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertEqual(
                    carried_output,
                    "Remove the hardcoded token in feature.txt.",
                )
                self.assertIn("Remove the hardcoded token in feature.txt.", prompt)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "token = os.environ['TOKEN']\n")
                self.commit_all(self.work_dir(task, repo_path), "fix: remove hardcoded token")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Removed the hardcoded token.",
                )

            def reviewer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Removed the hardcoded token.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after security fix.",
                )

            def security_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("feature.txt", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Security review passed.",
                )

            executor.handlers.update(
                {
                    ("developer", 1): developer_one,
                    ("code_reviewer", 1): reviewer_one,
                    ("security_reviewer", 1): security_one,
                    ("developer", 2): developer_two,
                    ("code_reviewer", 2): reviewer_two,
                    ("security_reviewer", 2): security_two,
                }
            )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "idle")

            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.step_visit_counts,
                {
                    "develop": 2,
                    "test": 2,
                    "code_review": 2,
                    "security_review": 2,
                    "merge_approval": 1,
                    "merge": 1,
                    "done": 1,
                },
            )
            self.assertEqual(
                executor.capture("developer", 2).carried_output,
                "Remove the hardcoded token in feature.txt.",
            )
            self.assertEqual(
                [
                    r.workflow_step
                    for r in store.list_runs(task_id=task.id)
                    if r.role_id != "_builtin:orchestrator"
                ],
                [
                    "develop",
                    "test",
                    "code_review",
                    "security_review",
                    "develop",
                    "test",
                    "code_review",
                    "security_review",
                    "merge_approval",
                    "merge",
                    "done",
                ],
            )

            transitions = [
                event.payload
                for event in store.list_events(task_id=task.id)
                if event.event_type == "workflow.transition"
            ]
            self.assertIn(
                {
                    "from_step": "security_review",
                    "to_step": "develop",
                    "trigger": "completion:deny",
                },
                transitions,
            )

    def test_review_feedback_and_test_failures_carry_output_back_into_development(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            executor = ScriptedAgentExecutor({})

            def developer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("Branch: feat/task-1", prompt)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "initial implementation\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: initial implementation")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Initial implementation complete.",
                )

            def developer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                # Tests run before review: the failure comes straight back.
                self.assertRegex(carried_output or "", r"^Tests failed in \d+\.\ds \(exit 1\)\.$")
                self.assertIn("(exit 1).", prompt)
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready now\n")
                self.commit_all(self.work_dir(task, repo_path), "fix: add ready marker")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Added the ready marker after test failure.",
                )

            def reviewer_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                # The reviewer sees the developer's summary, not the test output.
                self.assertIn("Added the ready marker after test failure.", prompt)
                return AgentExecutionResult(
                    outcome="deny",
                    detail="Please document the ready marker.",
                )

            def developer_three(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertEqual(carried_output, "Please document the ready marker.")
                self.assertIn("Please document the ready marker.", prompt)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "updated after review\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: address review guidance")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Updated after review feedback.",
                )

            def reviewer_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Updated after review feedback.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after the review fix.",
                )

            executor.handlers.update(
                {
                    ("developer", 1): developer_one,
                    ("developer", 2): developer_two,
                    ("code_reviewer", 1): reviewer_one,
                    ("developer", 3): developer_three,
                    ("code_reviewer", 2): reviewer_two,
                }
            )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            updated_task = store.get_task(task.id)
            self.assertIsNotNone(updated_task)
            assert updated_task is not None
            self.assertEqual(updated_task.status, "done")
            self.assertEqual(
                updated_task.step_visit_counts,
                {
                    "develop": 3,
                    "test": 3,
                    "review": 2,
                    "merge_approval": 1,
                    "merge": 1,
                    "done": 1,
                },
            )

            self.assertEqual(
                [
                    r.workflow_step
                    for r in store.list_runs(task_id=task.id)
                    if r.role_id != "_builtin:orchestrator"
                ],
                [
                    "develop",
                    "test",
                    "develop",
                    "test",
                    "review",
                    "develop",
                    "test",
                    "review",
                    "merge_approval",
                    "merge",
                    "done",
                ],
            )
            self.assertRegex(
                executor.capture("developer", 2).carried_output or "",
                r"^Tests failed in \d+\.\ds \(exit 1\)\.$",
            )
            self.assertEqual(
                executor.capture("developer", 3).carried_output,
                "Please document the ready marker.",
            )

            events = store.list_events(task_id=task.id)
            transitions = [
                event.payload
                for event in events
                if event.event_type == "workflow.transition"
            ]
            self.assertIn(
                {
                    "from_step": "review",
                    "to_step": "develop",
                    "trigger": "completion:deny",
                },
                transitions,
            )
            self.assertIn(
                {
                    "from_step": "test",
                    "to_step": "develop",
                    "trigger": "completion:failure",
                },
                transitions,
            )

    def test_model_ladder_escalates_developer_model_across_repeated_visits(self) -> None:
        """A role model_ladder escalates the develop model on each revisit and
        records the progression in ``workflow.model_selected`` events."""

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        # Inject a developer role whose model is chosen from a ladder.
        ladder = ("ladder-A", "ladder-B", "ladder-C")
        base_dev = self.roles["developer"]
        ladder_dev = replace(
            base_dev, agent=replace(base_dev.agent, model="", model_ladder=ladder)
        )
        roles = dict(self.roles)
        roles["developer"] = ladder_dev

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            executor = ScriptedAgentExecutor({})

            def developer_one(*, task, prompt, carried_output):
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "v1\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: v1")
                return AgentExecutionResult(outcome="done", detail="v1 done.")

            def developer_two(*, task, prompt, carried_output):
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "v2\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: v2")
                return AgentExecutionResult(outcome="done", detail="v2 done.")

            def developer_three(*, task, prompt, carried_output):
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "fix: ready marker")
                return AgentExecutionResult(outcome="done", detail="v3 done.")

            def reviewer_approve(*, task, prompt, carried_output):
                del task
                return AgentExecutionResult(outcome="approve", detail="Approved.")

            executor.handlers.update(
                {
                    # Two test failures escalate the ladder before review runs.
                    ("developer", 1): developer_one,
                    ("developer", 2): developer_two,
                    ("developer", 3): developer_three,
                    ("code_reviewer", 1): reviewer_approve,
                }
            )

            orchestrator = ForemanOrchestrator(
                store,
                roles=roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            result = orchestrator.run_project(project.id)
            self.assertEqual(result.executed_task_ids, (task.id,))

            # The develop runs should record escalating ladder models.
            develop_models = [
                run.model
                for run in store.list_runs(task_id=task.id)
                if run.workflow_step == "develop"
            ]
            self.assertEqual(develop_models, ["ladder-A", "ladder-B", "ladder-C"])

            # The workflow.model_selected events mirror that progression.
            selections = [
                event.payload
                for event in store.list_events(task_id=task.id)
                if event.event_type == "workflow.model_selected"
                and event.payload.get("step") == "develop"
            ]
            self.assertEqual(
                [(s["visit_count"], s["model"], s["source"]) for s in selections],
                [
                    (1, "ladder-A", "ladder"),
                    (2, "ladder-B", "ladder"),
                    (3, "ladder-C", "ladder"),
                ],
            )

    def test_tiered_triage_escalate_routes_to_frontier_review(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store, repo_path=repo_path, workflow_id="development_tiered"
            )
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            executor = ScriptedAgentExecutor({})

            def developer_one(*, task, prompt, carried_output):
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "impl\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement and ready")
                return AgentExecutionResult(outcome="done", detail="Implemented.")

            def triage_escalate(*, task, prompt, carried_output):
                del task
                return AgentExecutionResult(
                    outcome="escalate", detail="Touches auth; senior review needed."
                )

            def frontier_approve(*, task, prompt, carried_output):
                del task
                # The escalation reason should reach the frontier reviewer.
                self.assertIn("Touches auth", carried_output or "")
                return AgentExecutionResult(outcome="approve", detail="Approved by senior.")

            executor.handlers.update(
                {
                    ("developer", 1): developer_one,
                    ("triage_reviewer", 1): triage_escalate,
                    ("frontier_reviewer", 1): frontier_approve,
                }
            )

            orchestrator = ForemanOrchestrator(
                store, roles=self.roles, workflows=self.workflows, agent_executor=executor
            )
            result = orchestrator.run_project(project.id)
            self.assertEqual(result.executed_task_ids, (task.id,))

            steps = [
                r.workflow_step
                for r in store.list_runs(task_id=task.id)
                if r.role_id != "_builtin:orchestrator"
            ]
            self.assertEqual(
                steps, ["develop", "test", "triage", "review", "merge_approval", "merge", "done"]
            )
            # The escalate transition is recorded with its trigger.
            transitions = [
                event.payload
                for event in store.list_events(task_id=task.id)
                if event.event_type == "workflow.transition"
            ]
            self.assertIn(
                {"from_step": "triage", "to_step": "review", "trigger": "completion:escalate"},
                transitions,
            )

    def test_tiered_triage_approve_skips_frontier_review(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store, repo_path=repo_path, workflow_id="development_tiered"
            )
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)
            executor = ScriptedAgentExecutor({})

            def developer_one(*, task, prompt, carried_output):
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "impl\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement and ready")
                return AgentExecutionResult(outcome="done", detail="Implemented.")

            def triage_approve(*, task, prompt, carried_output):
                del task
                return AgentExecutionResult(outcome="approve", detail="Looks good.")

            executor.handlers.update(
                {
                    ("developer", 1): developer_one,
                    ("triage_reviewer", 1): triage_approve,
                }
            )

            orchestrator = ForemanOrchestrator(
                store, roles=self.roles, workflows=self.workflows, agent_executor=executor
            )
            result = orchestrator.run_project(project.id)
            self.assertEqual(result.executed_task_ids, (task.id,))

            role_ids = [r.role_id for r in store.list_runs(task_id=task.id)]
            self.assertIn("triage_reviewer", role_ids)
            self.assertNotIn("frontier_reviewer", role_ids)

    def test_completion_diff_only_populated_for_decision_roles(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store, repo_path=repo_path, workflow_id="development_tiered",
                acceptance_criteria="Implement the widget.",
                branch_name="feat/task-widget",
            )
            project.settings["review_diff_max_chars"] = 200
            store.save_project(project)

            self.git(repo_path, "checkout", "-b", task.branch_name)
            # Oversized file so the diff exceeds the cap and is truncated.
            self.write_text(repo_path / "widget.py", "x = 1\n" * 400)
            self.commit_all(repo_path, "feat: widget")
            self.git(repo_path, "checkout", "main")

            orchestrator = ForemanOrchestrator(
                store, roles=self.roles, workflows=self.workflows
            )
            task = store.get_task(task.id)
            developer_prompt = orchestrator.prompts.build(
                self.roles["developer"], project, task, None
            )
            triage_prompt = orchestrator.prompts.build(
                self.roles["triage_reviewer"], project, task, None
            )

            # Developer template carries no diff payload.
            self.assertNotIn("widget.py", developer_prompt)
            # Decision role gets the capped diff with the truncation marker.
            self.assertIn("widget.py", triage_prompt)
            self.assertIn("truncated", triage_prompt)

    def test_run_project_prunes_old_done_task_events_and_preserves_blocked_history(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        fixed_now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)
        cutoff = (fixed_now - timedelta(days=7)).isoformat(timespec="microseconds").replace("+00:00", "Z")

        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            project.settings["event_retention_days"] = 7
            store.save_project(project)

            blocked_task = Task(
                id="task-blocked",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Blocked historical task",
                status="blocked",
                blocked_reason="Waiting on approval",
                created_at="2026-03-01T12:00:00Z",
            )
            previous_sprint = Sprint(
                id="sprint-0",
                project_id=project.id,
                title="Earlier sprint",
                status="completed",
                created_at="2026-03-01T10:00:00Z",
                completed_at="2026-03-10T10:00:00Z",
            )
            done_task = Task(
                id="task-done-old",
                sprint_id=previous_sprint.id,
                project_id=project.id,
                title="Old completed task",
                status="done",
                created_at="2026-03-01T12:05:00Z",
                completed_at="2026-03-02T12:05:00Z",
            )
            store.save_sprint(previous_sprint)
            store.save_task(blocked_task)
            store.save_task(done_task)

            blocked_run = Run(
                id="run-blocked-old",
                task_id=blocked_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="failed",
                created_at="2026-03-01T12:10:00Z",
            )
            done_run = Run(
                id="run-done-old",
                task_id=done_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="done",
                agent_backend="claude_code",
                status="completed",
                created_at="2026-03-01T12:12:00Z",
            )
            store.save_run(blocked_run)
            store.save_run(done_run)

            blocked_event = Event(
                id="event-blocked-old",
                run_id=blocked_run.id,
                task_id=blocked_task.id,
                project_id=project.id,
                event_type="signal.blocker",
                timestamp="2026-03-01T12:15:00.000000Z",
                payload={"message": "Keep me"},
            )
            old_done_event = Event(
                id="event-done-old",
                run_id=done_run.id,
                task_id=done_task.id,
                project_id=project.id,
                event_type="signal.completion",
                timestamp="2026-03-01T12:20:00.000000Z",
                payload={"summary": "Prune me"},
            )
            store.save_event(blocked_event)
            store.save_event(old_done_event)

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "retention-safe implementation\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: finish pruning slice")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Finished the pruning slice.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Finished the pruning slice.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after review.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                    }
                ),
                utc_now=lambda: fixed_now,
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "blocked")
            self.assertIsNotNone(store.get_event(blocked_event.id))
            self.assertIsNone(store.get_event(old_done_event.id))

            pruned_events = [
                event
                for event in store.list_events(project_id=project.id)
                if event.event_type == "engine.event_pruned"
            ]
            self.assertEqual(len(pruned_events), 1)
            self.assertEqual(
                pruned_events[0].payload,
                {
                    "count": 1,
                    "older_than": cutoff,
                },
            )

    def test_missing_transition_uses_workflow_fallback_and_blocks_the_task(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                task_title="Handle unknown review outcome",
            )

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "implemented\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement fallback scenario")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the fallback scenario.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIn("Implemented the fallback scenario.", prompt)
                self.assertIsNone(carried_output)
                return AgentExecutionResult(
                    outcome="unknown",
                    detail="Outcome not mapped in the workflow.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                    }
                ),
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.blocked_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "blocked")

            blocked_task = store.get_task(task.id)
            self.assertIsNotNone(blocked_task)
            assert blocked_task is not None
            self.assertEqual(blocked_task.status, "blocked")
            self.assertEqual(
                blocked_task.blocked_reason,
                "Unhandled workflow outcome. Requires human review.",
            )

            events = store.list_events(task_id=task.id)
            no_transition = [
                event for event in events if event.event_type == "workflow.no_transition"
            ]
            self.assertEqual(len(no_transition), 1)
            self.assertEqual(
                no_transition[0].payload,
                {"step": "review", "outcome": "unknown"},
            )

    def test_run_project_writes_runtime_context_before_agent_runs_and_after_task_completion(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            project.settings["completion_guard_enabled"] = False
            store.save_project(project)

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del carried_output
                context_path = self.work_dir(task, repo_path) / ".foreman" / "context.md"
                status_path = self.work_dir(task, repo_path) / ".foreman" / "status.md"
                self.assertTrue(context_path.is_file())
                self.assertTrue(status_path.is_file())
                self.assertIn("Sprint: Orchestrator", context_path.read_text(encoding="utf-8"))
                self.assertIn(
                    "* [in_progress] Implement orchestrator loop (task-1)",
                    context_path.read_text(encoding="utf-8"),
                )
                self.assertIn("## Current Sprint Detail", status_path.read_text(encoding="utf-8"))
                self.assertIn("Title: Orchestrator", status_path.read_text(encoding="utf-8"))
                self.assertIn("# Sprint Context", prompt)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "implemented\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement workflow slice")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the workflow slice.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Implemented the workflow slice.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after review.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                    }
                ),
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "idle")
            context_text = (repo_path / ".foreman" / "context.md").read_text(encoding="utf-8")
            status_text = (repo_path / ".foreman" / "status.md").read_text(encoding="utf-8")
            self.assertIn("* [done] Implement orchestrator loop (task-1)", context_text)
            self.assertIn("Status: done", context_text)
            self.assertIn(
                "Task counts: todo=0 in_progress=0 blocked=0 done=1 cancelled=0",
                status_text,
            )

            context_events = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "engine.context_write"
            ]
            self.assertGreaterEqual(len(context_events), 4)
            self.assertIn(
                {"path": ".foreman/context.md"},
                [event.payload for event in context_events],
            )
            self.assertIn(
                {"path": ".foreman/status.md"},
                [event.payload for event in context_events],
            )

    def test_builtin_context_write_reuses_runtime_projection(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            workflow = WorkflowDefinition(
                id="development_with_context_write",
                name="Development With Context Write",
                methodology="development",
                steps=(
                    WorkflowStep(id="develop", role="developer"),
                    WorkflowStep(id="sync_context", role="_builtin:context_write"),
                    WorkflowStep(id="done", role="_builtin:mark_done"),
                ),
                transitions=(
                    WorkflowTransition(
                        from_step="develop",
                        trigger="completion:done",
                        to_step="sync_context",
                    ),
                    WorkflowTransition(
                        from_step="sync_context",
                        trigger="completion:success",
                        to_step="done",
                    ),
                ),
                gates=(),
                fallback=WorkflowFallback(
                    action="block",
                    message="Unhandled workflow outcome.",
                ),
                source_path=Path("tests"),
            )

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del carried_output
                self.assertIn("# Sprint Context", prompt)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "implemented\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement context-write workflow")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the workflow slice.",
                )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows={workflow.id: workflow},
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                    }
                ),
            )

            project.workflow_id = workflow.id
            store.save_project(project)
            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertTrue((repo_path / ".foreman" / "context.md").is_file())
            self.assertTrue((repo_path / ".foreman" / "status.md").is_file())

            runs = store.list_runs(task_id=task.id)
            workflow_runs = [r for r in runs if r.role_id != "_builtin:orchestrator"]
            self.assertEqual(
                [run.workflow_step for run in workflow_runs],
                ["develop", "sync_context", "done"],
            )
            context_events = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "engine.context_write"
            ]
            sync_context_run = next(run for run in runs if run.workflow_step == "sync_context")
            sync_context_payloads = [
                event.payload for event in context_events if event.run_id == sync_context_run.id
            ]
            # The projection is written into the project's context directory
            # and mirrored into the task worktree's own, so the agent finds it
            # where it works.
            self.assertEqual(
                sync_context_payloads,
                [
                    {"path": ".foreman/context.md", "schema_version": "1.0"},
                    {"path": ".foreman/status.md", "schema_version": "1.0"},
                    {
                        "path": ".foreman/worktrees/FD-1/.foreman/context.md",
                        "schema_version": "1.0",
                    },
                    {
                        "path": ".foreman/worktrees/FD-1/.foreman/status.md",
                        "schema_version": "1.0",
                    },
                ],
            )


if __name__ == "__main__":
    unittest.main()
