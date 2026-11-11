"""What an operator, a blocker, a limit or a dependency does to a task."""

from __future__ import annotations
import unittest
from foreman.models import Project, Run, Sprint, Task
from foreman.engine.results import AgentEventRecord, AgentExecutionResult
from foreman.orchestrator import ForemanOrchestrator
from foreman.store import ForemanStore

from engine_support import (
    OrchestratorTestCase,
    ScriptedAgentExecutor,
)


class TaskControlTests(OrchestratorTestCase):
    """What an operator, a blocker, a limit or a dependency does to a task."""

    def test_a_task_cancelled_mid_step_stays_cancelled_and_is_not_merged(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)

            def developer(*, task: Task, prompt: str, carried_output: str | None):
                # The operator cancels from another process while the agent works.
                with ForemanStore(db_path) as operator:
                    theirs = operator.get_task(task.id)
                    theirs.status = "cancelled"
                    theirs.title = "Renamed by the operator"
                    operator.save_task(theirs)
                (self.work_dir(task, repo_path) / "ready.txt").write_text("ok\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: work nobody wants")
                return AgentExecutionResult(outcome="done", detail="Implemented.")

            orchestrator, executor, _ = self._run_with_developer(store, project, developer)

            stored = store.get_task(task.id)
            self.assertEqual(stored.status, "cancelled")
            self.assertEqual(stored.title, "Renamed by the operator")
            self.assertEqual(executor.call_counts.get("code_reviewer", 0), 0)
            steps = [run.workflow_step for run in store.list_runs(task_id=task.id)]
            self.assertNotIn("merge", steps)
            self.assertNotIn("done", steps)
            self.assertEqual(
                [run.id for run in store.list_runs(task_id=task.id) if run.status == "running"], []
            )
            self.assertIsNone(
                store.get_active_lease(
                    project_id=project.id, resource_type="task", resource_id=task.id
                )
            )
            self.assertNotIn(
                "feat: work nobody wants",
                self.git(repo_path, "log", "--format=%s", "main").stdout,
            )

    def test_an_operator_edit_made_mid_step_survives_the_engines_next_write(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)

            def developer(*, task: Task, prompt: str, carried_output: str | None):
                with ForemanStore(db_path) as operator:
                    theirs = operator.get_task(task.id)
                    theirs.title = "Sharper title"
                    theirs.acceptance_criteria = "Sharper criteria."
                    theirs.priority = 7
                    operator.save_task(theirs)
                return AgentExecutionResult(outcome="error", detail="stop after one step")

            self._run_with_developer(store, project, developer)

            stored = store.get_task(task.id)
            self.assertEqual(stored.title, "Sharper title")
            self.assertEqual(stored.acceptance_criteria, "Sharper criteria.")
            self.assertEqual(stored.priority, 7)

    def test_a_blocker_reported_by_the_agent_stops_the_workflow(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)

            def developer(*, task: Task, prompt: str, carried_output: str | None):
                (self.work_dir(task, repo_path) / "ready.txt").write_text("ok\n")
                self.commit_all(self.work_dir(task, repo_path), "feat: implement")
                return AgentExecutionResult(
                    outcome="done",
                    detail="Implemented, but something is in the way.",
                    events=(
                        AgentEventRecord(
                            event_type="signal.blocker",
                            payload={"message": "Need credentials for the staging API."},
                        ),
                    ),
                )

            orchestrator, executor, result = self._run_with_developer(store, project, developer)

            stored = store.get_task(task.id)
            self.assertEqual(stored.status, "blocked")
            self.assertEqual(stored.blocked_reason, "Need credentials for the staging API.")
            self.assertEqual(executor.call_counts.get("code_reviewer", 0), 0)
            self.assertNotIn(
                "merge", [run.workflow_step for run in store.list_runs(task_id=task.id)]
            )
            self.assertIn(task.id, result.blocked_task_ids)

    def test_a_zero_cost_limit_means_no_limit(self) -> None:
        """0 is the documented off value and what the settings screen saves."""

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                workflow_id="development",
                default_branch="main",
                settings={"cost_limit_per_task_usd": 0, "cost_limit_per_sprint_usd": 0.0},
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Unbudgeted sprint",
                status="active",
                created_at="2026-03-30T12:05:00Z",
                started_at="2026-03-30T12:10:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Must not be blocked by a zero limit",
                status="todo",
                created_at="2026-03-30T12:15:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)

            executor = ScriptedAgentExecutor(
                {"developer": [AgentExecutionResult(outcome="error", detail="stop here")]}
            )
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=executor,
            )
            orchestrator.run_project(project.id)

            self.assertEqual(
                [e for e in store.list_events(task_id=task.id) if e.event_type == "gate.cost_exceeded"],
                [],
            )
            self.assertNotIn("exceeds limit", store.get_task(task.id).blocked_reason or "")
            self.assertTrue(
                any(run.role_id == "developer" for run in store.list_runs(task_id=task.id)),
                "the developer step should have run",
            )

    def test_sprint_cost_limit_blocks_task_before_next_step_runs(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                workflow_id="development",
                default_branch="main",
                settings={"cost_limit_per_sprint_usd": 5.0},
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Budgeted sprint",
                status="active",
                created_at="2026-03-30T12:05:00Z",
                started_at="2026-03-30T12:10:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Blocked by sprint budget",
                status="todo",
                created_at="2026-03-30T12:15:00Z",
            )
            prior_task = Task(
                id="task-prior",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Earlier expensive task",
                status="done",
                created_at="2026-03-30T12:14:00Z",
                completed_at="2026-03-30T12:14:30Z",
            )
            prior_run = Run(
                id="run-prior",
                task_id=prior_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="codex",
                status="completed",
                outcome="done",
                cost_usd=5.25,
                token_count=250,
                created_at="2026-03-30T12:14:00Z",
                started_at="2026-03-30T12:14:00Z",
                completed_at="2026-03-30T12:14:30Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(prior_task)
            store.save_task(task)
            store.save_run(prior_run)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
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
                "Sprint cost $5.25 exceeds limit $5.00",
            )
            # A task parked by a gate is not being worked on: no lease is held.
            self.assertIsNone(
                store.get_active_lease(
                    project_id=project.id, resource_type="task", resource_id=task.id
                )
            )
            self.assertEqual(orchestrator.leases.heartbeats, {})

            runs = store.list_runs(task_id=task.id)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].role_id, "_builtin:orchestrator")
            self.assertEqual(runs[0].outcome, "blocked")

            cost_events = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "gate.cost_exceeded"
            ]
            self.assertEqual(len(cost_events), 1)
            self.assertEqual(
                cost_events[0].payload,
                {
                    "limit_usd": 5.0,
                    "actual_usd": 5.25,
                    "scope": "sprint",
                },
            )

    def test_select_next_task_blocks_a_task_whose_dependency_was_cancelled(self) -> None:
        repo_path, db_path = self.create_workspace()
        repo_path.mkdir(exist_ok=True)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                workflow_id="development",
                default_branch="main",
                settings={"task_selection_mode": "directed"},
            )
            sprint = Sprint(id="sprint-1", project_id=project.id, title="S", status="active")
            cancelled = Task(
                id="task-dep",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Prerequisite that was dropped",
                status="cancelled",
                priority=0,
            )
            dependent = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Builds on the prerequisite",
                status="todo",
                priority=1,
                depends_on_task_ids=["task-dep"],
            )
            ready = Task(
                id="task-2",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Independent work",
                status="todo",
                priority=2,
            )
            for row in (project,):
                store.save_project(row)
            store.save_sprint(sprint)
            for task in (cancelled, dependent, ready):
                store.save_task(task)
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=ScriptedAgentExecutor({}),
            )

            selected = orchestrator.select_next_task(project)

            self.assertIsNotNone(selected)
            assert selected is not None
            self.assertEqual(selected.id, "task-2", "a cancelled prerequisite never releases the dependent")
            parked = store.get_task("task-1")
            assert parked is not None
            self.assertEqual(parked.status, "blocked")
            self.assertIn("Dependency cancelled: task-dep", parked.blocked_reason or "")
            attention = [
                event.payload
                for event in store.list_events(task_id="task-1")
                if event.event_type == "engine.attention_needed"
            ]
            self.assertEqual(len(attention), 1)
            self.assertEqual(attention[0].get("trigger"), "dependency_cancelled")

            # Blocking is idempotent: a second selection pass leaves one block.
            orchestrator.leases.release(selected, project)
            orchestrator.select_next_task(project)
            self.assertEqual(
                len([e for e in store.list_events(task_id="task-1") if e.event_type == "engine.attention_needed"]),
                1,
            )

    def test_select_next_task_skips_unsatisfied_dependencies(self) -> None:
        repo_path, db_path = self.create_workspace()
        repo_path.mkdir(exist_ok=True)

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                workflow_id="development",
                default_branch="main",
                settings={"task_selection_mode": "directed"},
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Orchestrator",
                status="active",
                created_at="2026-03-30T12:05:00Z",
                started_at="2026-03-30T12:10:00Z",
            )
            blocked_task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Blocked by dependency",
                status="todo",
                priority=0,
                depends_on_task_ids=["task-missing"],
                created_at="2026-03-30T12:15:00Z",
            )
            ready_task = Task(
                id="task-2",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Ready task",
                status="todo",
                priority=1,
                created_at="2026-03-30T12:16:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(blocked_task)
            store.save_task(ready_task)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
            )

            selected = orchestrator.select_next_task(project)

            self.assertIsNotNone(selected)
            assert selected is not None
            self.assertEqual(selected.id, ready_task.id)


if __name__ == "__main__":
    unittest.main()
