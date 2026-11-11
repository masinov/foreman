"""Leases, stale runs and what a crash leaves behind."""

from __future__ import annotations
from datetime import datetime, timezone
import unittest
from foreman.models import Event, Run, Task
from foreman.engine.errors import OrchestratorError
from foreman.engine.results import AgentExecutionResult
from foreman.orchestrator import ForemanOrchestrator
from foreman.runner.process import EngineShutdown
from foreman.store import ForemanStore

from engine_support import (
    OrchestratorTestCase,
    ScriptedAgentExecutor,
)


class RecoveryAndLeaseTests(OrchestratorTestCase):
    """Leases, stale runs and what a crash leaves behind."""

    def test_run_project_waits_for_non_stale_active_run_before_starting_other_tasks(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            project.settings["time_limit_per_run_minutes"] = 10
            store.save_project(project)
            task.status = "in_progress"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            waiting_task = Task(
                id="task-2",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Second task",
                status="todo",
                created_at="2026-03-30T12:21:00Z",
            )
            store.save_task(waiting_task)
            active_run = Run(
                id="run-active",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(active_run)
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                utc_now=lambda: datetime(2026, 3, 30, 12, 25, 0, tzinfo=timezone.utc),
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.executed_task_ids, ())
            self.assertEqual(result.stop_reason, "waiting")
            refreshed_waiting_task = store.get_task(waiting_task.id)
            assert refreshed_waiting_task is not None
            self.assertEqual(refreshed_waiting_task.status, "todo")

    def test_project_run_task_rejects_non_stale_active_running_run(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["time_limit_per_run_minutes"] = 10
            store.save_project(project)
            task.status = "in_progress"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            active_run = Run(
                id="run-active",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(active_run)
            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                utc_now=lambda: datetime(2026, 3, 30, 12, 25, 0, tzinfo=timezone.utc),
            )

            with self.assertRaises(OrchestratorError) as exc:
                orchestrator.run_project(project.id, task_id=task.id)

            self.assertIn("already has an active run", str(exc.exception))
            refreshed_task = store.get_task(task.id)
            assert refreshed_task is not None
            self.assertEqual(refreshed_task.status, "in_progress")
            refreshed_run = store.get_run(active_run.id)
            assert refreshed_run is not None
            self.assertEqual(refreshed_run.status, "running")

    def test_recover_orphaned_tasks_only_recovers_stale_running_runs(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["time_limit_per_run_minutes"] = 1
            store.save_project(project)
            task.status = "in_progress"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            fresh_task = Task(
                id="task-2",
                sprint_id=task.sprint_id,
                project_id=project.id,
                title="Fresh in-progress task",
                status="in_progress",
                branch_name="feat/task-2-fresh",
                started_at="2026-03-30T12:29:30Z",
                created_at="2026-03-30T12:29:00Z",
            )
            store.save_task(fresh_task)
            stale_run = Run(
                id="run-stale",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(stale_run)
            fresh_run = Run(
                id="run-fresh",
                task_id=fresh_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:29:30Z",
                created_at="2026-03-30T12:29:30Z",
            )
            store.save_run(fresh_run)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                utc_now=lambda: datetime(2026, 3, 30, 12, 30, 0, tzinfo=timezone.utc),
            )

            orchestrator.recover_orphaned_tasks(project.id)

            refreshed_task = store.get_task(task.id)
            assert refreshed_task is not None
            self.assertEqual(refreshed_task.status, "todo")
            self.assertEqual(refreshed_task.step_visit_counts, {})
            refreshed_run = store.get_run(stale_run.id)
            assert refreshed_run is not None
            self.assertEqual(refreshed_run.status, "failed")
            self.assertEqual(
                refreshed_run.outcome_detail,
                "Recovered stale running run after exceeding the active-run limit.",
            )
            refreshed_fresh_task = store.get_task(fresh_task.id)
            assert refreshed_fresh_task is not None
            self.assertEqual(refreshed_fresh_task.status, "in_progress")
            refreshed_fresh_run = store.get_run(fresh_run.id)
            assert refreshed_fresh_run is not None
            self.assertEqual(refreshed_fresh_run.status, "running")

    def test_recover_orphaned_tasks_uses_latest_event_timestamp_for_liveness(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            project.settings["time_limit_per_run_minutes"] = 240
            project.settings["active_run_recovery_timeout_minutes"] = 5
            store.save_project(project)
            task.status = "in_progress"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            fresh_task = Task(
                id="task-2",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Fresh in-progress task",
                status="in_progress",
                branch_name="feat/task-2-fresh",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:19:00Z",
            )
            store.save_task(fresh_task)
            stale_run = Run(
                id="run-stale",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(stale_run)
            fresh_run = Run(
                id="run-fresh",
                task_id=fresh_task.id,
                project_id=project.id,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(fresh_run)
            store.save_event(
                Event(
                    id="event-review-heartbeat",
                    run_id=fresh_run.id,
                    task_id=fresh_task.id,
                    project_id=project.id,
                    event_type="agent.started",
                    role_id="code_reviewer",
                    timestamp="2026-03-30T12:29:30Z",
                    payload={"phase": "review"},
                )
            )

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                utc_now=lambda: datetime(2026, 3, 30, 12, 30, 0, tzinfo=timezone.utc),
            )

            orchestrator.recover_orphaned_tasks(project.id)

            refreshed_task = store.get_task(task.id)
            assert refreshed_task is not None
            self.assertEqual(refreshed_task.status, "todo")
            refreshed_run = store.get_run(stale_run.id)
            assert refreshed_run is not None
            self.assertEqual(refreshed_run.status, "failed")
            refreshed_fresh_task = store.get_task(fresh_task.id)
            assert refreshed_fresh_task is not None
            self.assertEqual(refreshed_fresh_task.status, "in_progress")
            refreshed_fresh_run = store.get_run(fresh_run.id)
            assert refreshed_fresh_run is not None
            self.assertEqual(refreshed_fresh_run.status, "running")

    def test_the_lease_heartbeat_runs_only_while_run_task_does(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            seen: dict[str, bool] = {}

            class Probe(ScriptedAgentExecutor):
                def execute(inner, *args, **kwargs):  # noqa: N805
                    seen["during"] = task.id in orchestrator.leases.heartbeats
                    return super().execute(*args, **kwargs)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                agent_executor=Probe(
                    {"developer": [AgentExecutionResult(outcome="error", detail="stop here")]}
                ),
            )
            orchestrator.run_project(project.id)

            self.assertTrue(seen.get("during"), "the lease must be heartbeated during a step")
            self.assertEqual(orchestrator.leases.heartbeats, {})

    def test_an_engine_error_inside_a_step_does_not_leave_a_running_run(self) -> None:
        from unittest import mock

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)

            def developer(*, task: Task, prompt: str, carried_output: str | None):
                tree = self.work_dir(task, repo_path)
                (tree / "ready.txt").write_text("ok\n")
                self.commit_all(tree, "feat: implement")
                return AgentExecutionResult(outcome="done", detail="Implemented.")

            executor = ScriptedAgentExecutor({("developer", 1): developer})
            orchestrator = ForemanOrchestrator(
                store, roles=self.roles, workflows=self.workflows, agent_executor=executor
            )
            with mock.patch.object(
                orchestrator.builtin_executor, "execute", side_effect=ValueError("built-in exploded")
            ):
                with self.assertRaises(Exception) as caught:
                    orchestrator.run_project(project.id)
            self.assertIn("built-in exploded", str(caught.exception))

            runs = store.list_runs(task_id=task.id)
            self.assertEqual([run.id for run in runs if run.status == "running"], [])
            failed = [run for run in runs if run.workflow_step == "test"]
            self.assertEqual([run.status for run in failed], ["failed"])
            self.assertIn("built-in exploded", failed[0].outcome_detail)

    def test_a_crash_between_two_steps_resumes_at_the_next_step(self) -> None:
        from unittest import mock

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)

            def developer(*, task: Task, prompt: str, carried_output: str | None):
                tree = self.work_dir(task, repo_path)
                (tree / "ready.txt").write_text("ok\n")
                self.commit_all(tree, "feat: implement")
                return AgentExecutionResult(outcome="done", detail="Implemented the loop.")

            def reviewer(*, task: Task, prompt: str, carried_output: str | None):
                return AgentExecutionResult(outcome="approve", detail="Approved.")

            executor = ScriptedAgentExecutor(
                {("developer", 1): developer, ("code_reviewer", 1): reviewer}
            )
            crashing = ForemanOrchestrator(
                store, roles=self.roles, workflows=self.workflows, agent_executor=executor
            )
            # The engine dies right after develop hands over to test.
            with mock.patch.object(
                crashing.leases, "renew", side_effect=EngineShutdown("SIGKILL")
            ):
                with self.assertRaises(EngineShutdown):
                    crashing.run_project(project.id)
            crashing.release_task(task.id)  # a dead engine's lease expires; skip the wait

            stored = store.get_task(task.id)
            self.assertEqual(stored.status, "in_progress")
            self.assertEqual(stored.workflow_current_step, "test")

            restarted = ForemanOrchestrator(
                store, roles=self.roles, workflows=self.workflows, agent_executor=executor
            )
            restarted.run_project(project.id)

            self.assertEqual(executor.call_counts.get("developer", 0), 1)
            self.assertEqual(executor.call_counts.get("code_reviewer", 0), 1)
            steps = [
                run.workflow_step
                for run in store.list_runs(task_id=task.id)
                if run.role_id != "_builtin:orchestrator"
            ]
            self.assertEqual(steps[:3], ["develop", "test", "review"])
            test_run = next(
                run for run in store.list_runs(task_id=task.id) if run.workflow_step == "test"
            )
            self.assertIsNotNone(test_run.duration_ms)
            self.assertGreaterEqual(test_run.duration_ms, 0)

    def test_stale_run_recovery_does_not_cost_the_engine_its_own_lease(self) -> None:
        """``run_task`` recovers stale runs while holding the lease it just took."""

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            task.status = "in_progress"
            store.save_task(task)
            stale_run = Run(
                id="run-stale",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(stale_run)
            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
            self.addCleanup(orchestrator.close)
            self.assertIsNotNone(orchestrator.leases.acquire(task, project))

            orchestrator.recovery.recover_stale_running_runs(project, task, [stale_run])

            self.assertEqual(store.get_run(stale_run.id).status, "failed")
            self.assertTrue(orchestrator.leases.renew(task, project))
            lease = store.get_active_lease(
                project_id=project.id, resource_type="task", resource_id=task.id
            )
            self.assertIsNotNone(lease)
            self.assertEqual(lease.holder_id, orchestrator.holder_id)

    def test_recover_stale_running_runs_expires_active_task_lease(self) -> None:
        """Recovery must force-expire the active task lease so the next
        orchestrator can acquire it without waiting for ``expires_at``.
        """
        from foreman.leases import generate_lease_token

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        # Crashed-orchestrator clock: the lease was acquired long ago and
        # its heartbeat has not been refreshed since. From the new
        # orchestrator's perspective the holder is gone.
        crash_clock = datetime(2026, 3, 30, 12, 20, 0, tzinfo=timezone.utc)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["time_limit_per_run_minutes"] = 1
            store.save_project(project)
            task.status = "in_progress"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            # Acquire the lease as the crashed holder at the crash clock,
            # then rewind its heartbeat by direct SQL so the liveness check
            # treats the holder as gone.
            lease_token = generate_lease_token()
            lease = store.acquire_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
                holder_id="crashed-holder",
                lease_token=lease_token,
                duration_seconds=600.0,
            )
            assert lease is not None
            store._connection.execute(
                "UPDATE leases SET heartbeat_at = ?, acquired_at = ? WHERE id = ?",
                (
                    crash_clock.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    crash_clock.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    lease.id,
                ),
            )
            stale_run = Run(
                id="run-stale",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(stale_run)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                utc_now=lambda: datetime(2026, 3, 30, 12, 30, 0, tzinfo=timezone.utc),
            )

            orchestrator.recover_orphaned_tasks(project.id)

            # Run and task should be reset.
            refreshed_run = store.get_run(stale_run.id)
            assert refreshed_run is not None
            self.assertEqual(refreshed_run.status, "failed")
            refreshed_task = store.get_task(task.id)
            assert refreshed_task is not None
            self.assertEqual(refreshed_task.status, "todo")

            # The active task lease must be expired so a new orchestrator can
            # acquire it without waiting for ``expires_at``.
            active_lease = store.get_active_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
            )
            self.assertIsNone(active_lease)

            expired_leases = store.list_leases(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
                status="expired",
            )
            self.assertEqual(len(expired_leases), 1)
            self.assertEqual(expired_leases[0].id, lease.id)

    def test_recover_stale_running_runs_crash_event_omits_lease_token(self) -> None:
        """``engine.crash_recovery`` events must not leak ``lease_token``;
        lease tokens are secrets and must not be persisted in event history.
        """
        from foreman.leases import generate_lease_token

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        crash_clock = datetime(2026, 3, 30, 12, 20, 0, tzinfo=timezone.utc)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["time_limit_per_run_minutes"] = 1
            store.save_project(project)
            task.status = "in_progress"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            lease_token = generate_lease_token()
            lease = store.acquire_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
                holder_id="crashed-holder",
                lease_token=lease_token,
            )
            assert lease is not None
            store._connection.execute(
                "UPDATE leases SET heartbeat_at = ?, acquired_at = ? WHERE id = ?",
                (
                    crash_clock.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    crash_clock.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    lease.id,
                ),
            )
            stale_run = Run(
                id="run-stale",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(stale_run)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                utc_now=lambda: datetime(2026, 3, 30, 12, 30, 0, tzinfo=timezone.utc),
            )

            orchestrator.recover_orphaned_tasks(project.id)

            events = store.list_events(task_id=task.id)
            recovery_events = [
                event for event in events
                if event.event_type == "engine.crash_recovery"
            ]
            self.assertGreaterEqual(len(recovery_events), 1)
            for event in recovery_events:
                self.assertNotIn("lease_token", event.payload)

    def test_run_is_stale_treats_lease_held_by_other_holder_as_live(self) -> None:
        """A run whose task lease is held by a different orchestrator must
        not be considered stale while that holder is heartbeating.
        """
        from foreman.leases import generate_lease_token

        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["time_limit_per_run_minutes"] = 1
            store.save_project(project)
            task.status = "in_progress"
            task.branch_name = "feat/task-1-implement-orchestrator-loop"
            task.started_at = "2026-03-30T12:20:00Z"
            store.save_task(task)
            # Another orchestrator holds an active lease with a recent
            # heartbeat, so this run is still owned by a different process.
            live_lease = store.acquire_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
                holder_id="other-holder",
                lease_token=generate_lease_token(),
            )
            assert live_lease is not None
            recent_heartbeat = "2026-03-30T12:29:30.000000Z"
            store._connection.execute(
                "UPDATE leases SET heartbeat_at = ?, acquired_at = ? WHERE id = ?",
                (recent_heartbeat, recent_heartbeat, live_lease.id),
            )
            stale_run = Run(
                id="run-active-other-holder",
                task_id=task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
                started_at="2026-03-30T12:20:00Z",
                created_at="2026-03-30T12:20:00Z",
            )
            store.save_run(stale_run)

            orchestrator = ForemanOrchestrator(
                store,
                roles=self.roles,
                workflows=self.workflows,
                holder_id="this-holder",
                utc_now=lambda: datetime(2026, 3, 30, 12, 30, 0, tzinfo=timezone.utc),
            )

            self.assertFalse(
                orchestrator.recovery.run_is_stale(project, stale_run),
                "Run with a live lease held by another holder must not be stale.",
            )

            # The stale-check must not have touched the run.
            refreshed_run = store.get_run(stale_run.id)
            assert refreshed_run is not None
            self.assertEqual(refreshed_run.status, "running")


if __name__ == "__main__":
    unittest.main()
