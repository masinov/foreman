"""Pausing at a human gate and carrying out the decision."""

from __future__ import annotations
import unittest
from foreman.models import Task
from foreman.engine.results import AgentExecutionResult
from foreman.orchestrator import ForemanOrchestrator
from foreman.store import ForemanStore

from engine_support import (
    OrchestratorTestCase,
    ScriptedAgentExecutor,
)


class HumanGateTests(OrchestratorTestCase):
    """Pausing at a human gate and carrying out the decision."""

    def test_human_gate_approve_resumes_workflow_and_finishes_the_task(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_with_architect",
                task_title="Approve the architect plan",
                branch_name="feat/task-1",
            )
            executor = ScriptedAgentExecutor({})

            def architect_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("Title: Approve the architect plan", prompt)
                self.write_text(self.work_dir(task, repo_path) / "plan.md", "Initial plan\n")
                self.commit_all(self.work_dir(task, repo_path), "docs: capture initial plan")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Architect plan ready for approval.",
                )

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("## Task: Approve the architect plan", prompt)
                self.write_text(self.work_dir(task, repo_path) / "plan.md", "approved plan\n")
                # Commit concrete files on the branch; file names contain keywords
                # from the task acceptance criteria "Task reaches done after review,
                # test, and merge." so the completion guard can assess them.
                (self.work_dir(task, repo_path) / "plan_review.py").write_text("def review(): pass\n")
                (self.work_dir(task, repo_path) / "plan_test.py").write_text("def test(): pass\n")
                (self.work_dir(task, repo_path) / "plan_merge.py").write_text("def merge(): pass\n")
                (self.work_dir(task, repo_path) / "ready.txt").write_text("ok\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement approved plan")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the approved plan.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Implemented the approved plan.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after review.",
                )

            executor.handlers.update(
                {
                    ("architect", 1): architect_handler,
                    ("developer", 1): developer_handler,
                    ("code_reviewer", 1): reviewer_handler,
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            first_result = orchestrator.run_project(project.id)

            self.assertEqual(first_result.executed_task_ids, (task.id,))
            self.assertEqual(first_result.blocked_task_ids, (task.id,))

            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )
            resume_result = resume_orchestrator.resume_human_gate(
                task.id,
                outcome="approve",
                note="looks good",
            )

            self.assertFalse(resume_result.deferred)
            self.assertEqual(resume_result.paused_step, "human_approval")
            self.assertEqual(resume_result.next_step, "develop")
            self.assertEqual(resume_result.task.status, "done")
            self.assertIsNone(resume_result.task.workflow_current_step)

            runs = store.list_runs(task_id=task.id)
            self.assertEqual(
                [run.workflow_step for run in runs if run.role_id != "_builtin:orchestrator"],
                ["plan", "human_approval", "human_approval", "develop", "test", "review", "merge_approval", "merge", "done"],
            )
            self.assertEqual(
                [run.outcome for run in runs],
                ["done", "paused", "approve", "done", "success", "approve", "approve", "success", "success"],
            )

            resumed_events = [
                event.payload
                for event in store.list_events(task_id=task.id)
                if event.event_type == "workflow.resumed"
            ]
            self.assertEqual(
                resumed_events,
                [
                    {
                        "step": "human_approval",
                        "decision": "approve",
                        "next_step": "develop",
                        "deferred": False,
                        "note": "looks good",
                    }
                ],
            )

    def test_a_deferred_approval_is_a_decision_the_engine_then_carries_out(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_with_architect",
                task_title="Approve the architect plan",
                branch_name="feat/task-1",
            )
            executor = ScriptedAgentExecutor({})

            def architect_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("Title: Approve the architect plan", prompt)
                self.write_text(self.work_dir(task, repo_path) / "plan.md", "Initial plan\n")
                self.commit_all(self.work_dir(task, repo_path), "docs: capture initial plan")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Architect plan ready for approval.",
                )

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.assertIn("## Task: Approve the architect plan", prompt)
                self.write_text(self.work_dir(task, repo_path) / "plan.md", "approved plan\n")
                # Commit concrete files on the branch; file names contain keywords
                # from the task acceptance criteria "Task reaches done after review,
                # test, and merge." so the completion guard can assess them.
                (self.work_dir(task, repo_path) / "plan_review.py").write_text("def review(): pass\n")
                (self.work_dir(task, repo_path) / "plan_test.py").write_text("def test(): pass\n")
                (self.work_dir(task, repo_path) / "plan_merge.py").write_text("def merge(): pass\n")
                (self.work_dir(task, repo_path) / "ready.txt").write_text("ok\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement approved plan")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented the approved plan.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIsNone(carried_output)
                self.assertIn("Implemented the approved plan.", prompt)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after review.",
                )

            executor.handlers.update(
                {
                    ("architect", 1): architect_handler,
                    ("developer", 1): developer_handler,
                    ("code_reviewer", 1): reviewer_handler,
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            first_result = orchestrator.run_project(project.id)

            self.assertEqual(first_result.executed_task_ids, (task.id,))
            self.assertEqual(first_result.blocked_task_ids, (task.id,))

            # The approver is not an engine: it records the decision and stops,
            # even though it could run the next step itself.
            approver = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )
            decision = approver.resume_human_gate(
                task.id, outcome="approve", note="looks good", defer=True
            )

            self.assertTrue(decision.deferred)
            self.assertEqual(decision.task.status, "in_progress")
            self.assertEqual(decision.task.workflow_current_step, "develop")
            self.assertEqual(executor.call_counts.get("developer", 0), 0)
            recorded = store._connection.execute(
                "SELECT decision FROM human_gate_decisions WHERE task_id = ?", (task.id,)
            ).fetchall()
            self.assertEqual([row["decision"] for row in recorded], ["approve"])

            # The engine's next pass continues from the step the decision led to.
            second_result = orchestrator.run_project(project.id)

            self.assertEqual(second_result.executed_task_ids, (task.id,))
            self.assertEqual(store.get_task(task.id).status, "done")
            self.assertEqual(executor.call_counts.get("developer", 0), 1)

    def test_human_gate_deny_carries_the_note_back_into_planning(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_with_architect",
                task_title="Rework the architect plan",
            )
            executor = ScriptedAgentExecutor({})

            def architect_one(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.write_text(self.work_dir(task, repo_path) / "plan.md", "Initial plan\n")
                self.commit_all(self.work_dir(task, repo_path), "docs: draft initial plan")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Initial plan ready.",
                )

            def architect_two(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertEqual(carried_output, "rethink the approach")
                self.assertIn("rethink the approach", prompt)
                self.write_text(self.work_dir(task, repo_path) / "plan.md", "Revised plan\n")
                self.commit_all(self.work_dir(task, repo_path), "docs: revise plan after denial")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Revised plan ready.",
                )

            executor.handlers.update(
                {
                    ("architect", 1): architect_one,
                    ("architect", 2): architect_two,
                }
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )

            first_result = orchestrator.run_project(project.id)

            self.assertEqual(first_result.stop_reason, "blocked")
            resume_orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )
            resume_result = resume_orchestrator.resume_human_gate(
                task.id,
                outcome="deny",
                note="rethink the approach",
            )

            self.assertFalse(resume_result.deferred)
            self.assertEqual(resume_result.next_step, "plan")
            self.assertEqual(resume_result.task.status, "blocked")
            self.assertEqual(resume_result.task.workflow_current_step, "human_approval")
            self.assertEqual(
                resume_result.task.step_visit_counts,
                {"plan": 2, "human_approval": 2},
            )

            runs = store.list_runs(task_id=task.id)
            self.assertEqual(
                [run.workflow_step for run in runs if run.role_id != "_builtin:orchestrator"],
                ["plan", "human_approval", "human_approval", "plan", "human_approval"],
            )
            self.assertEqual(
                [run.outcome for run in runs],
                ["done", "paused", "deny", "done", "paused"],
            )

    def test_human_gate_resume_defers_when_the_next_backend_is_unavailable(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(
                store,
                repo_path=repo_path,
                workflow_id="development_with_architect",
                task_title="Resume after bootstrap approval",
                branch_name="feat/task-1-resume-after-bootstrap-approval",
            )
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
                acceptance_criteria=task.acceptance_criteria,
                blocked_reason="Awaiting human approval",
                workflow_current_step="human_approval",
                created_at=task.created_at,
                started_at="2026-03-30T12:20:00Z",
            )
            store.save_task(blocked_task)
            unavailable_roles = self.roles_with_backend("missing_backend")

            bootstrap_orchestrator = ForemanOrchestrator(
                store,
                roles=unavailable_roles,
                workflows=self.workflows,
            )
            resume_result = bootstrap_orchestrator.resume_human_gate(
                task.id,
                outcome="approve",
            )

            self.assertTrue(resume_result.deferred)
            self.assertEqual(resume_result.task.status, "in_progress")
            self.assertEqual(resume_result.task.workflow_current_step, "develop")
            self.assertIsNone(resume_result.task.blocked_reason)

            def developer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                self.assertIsNone(carried_output)
                self.write_text(self.work_dir(task, repo_path) / "feature.txt", "implemented after defer\n")
                self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
                self.write_text(self.work_dir(task, repo_path) / "deferred_task.py", "def done(): pass\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: finish deferred task")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Finished after deferred resume.",
                )

            def reviewer_handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
                del task
                self.assertIn("Finished after deferred resume.", prompt)
                self.assertIsNone(carried_output)
                return AgentExecutionResult(
                    outcome="approve",
                    detail="Approved after deferred resume.",
                )

            runner_orchestrator = ForemanOrchestrator(
                store,
                roles=unavailable_roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor(
                    {
                        ("developer", 1): developer_handler,
                        ("code_reviewer", 1): reviewer_handler,
                    }
                ),
            )

            result = runner_orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, (task.id,))
            self.assertEqual(result.stop_reason, "idle")
            final_task = store.get_task(task.id)
            self.assertIsNotNone(final_task)
            assert final_task is not None
            self.assertEqual(final_task.status, "done")


if __name__ == "__main__":
    unittest.main()
