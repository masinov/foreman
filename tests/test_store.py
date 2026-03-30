"""Round-trip tests for the SQLite-backed Foreman store."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from foreman.models import Event, Project, Run, Sprint, Task, utc_now_text
from foreman.store import ForemanStore


class ForemanStoreTests(unittest.TestCase):
    """Verify that the baseline SQLite store matches the core spec entities."""

    def create_db_path(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / "foreman.db"

    def test_initialize_is_idempotent_and_round_trips_core_entities(self) -> None:
        db_path = self.create_db_path()
        project = Project(
            id="project-1",
            name="Foreman",
            repo_path="/work/foreman",
            spec_path="docs/specs/engine-design-v3.md",
            workflow_id="development",
            settings={
                "default_model": "gpt-5.4",
                "context_dir": ".foreman",
                "max_step_visits": 5,
            },
            created_at="2026-03-30T10:00:00Z",
            updated_at="2026-03-30T10:00:00Z",
        )
        sprint = Sprint(
            id="sprint-1",
            project_id=project.id,
            title="Foundation",
            goal="Land the SQLite store baseline",
            status="active",
            order_index=1,
            created_at="2026-03-30T10:05:00Z",
            started_at="2026-03-30T10:10:00Z",
        )
        task = Task(
            id="task-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Persist entities",
            description="Implement the baseline store layer.",
            status="in_progress",
            task_type="feature",
            priority=2,
            order_index=3,
            branch_name="feat/sqlite-store-baseline",
            assigned_role="developer",
            acceptance_criteria="Round-trip project, sprint, task, run, and event rows.",
            created_by="agent:developer",
            depends_on_task_ids=["task-0"],
            workflow_current_step="develop",
            workflow_carried_output="carry this into review",
            step_visit_counts={"develop": 1},
            created_at="2026-03-30T10:15:00Z",
            started_at="2026-03-30T10:16:00Z",
        )
        run = Run(
            id="run-1",
            task_id=task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="codex",
            status="completed",
            outcome="done",
            outcome_detail="Implemented and tested.",
            model="gpt-5.4",
            session_id="session-1",
            branch_name="feat/sqlite-store-baseline",
            prompt_text="Build the store.",
            cost_usd=1.25,
            token_count=2048,
            duration_ms=120000,
            retry_count=1,
            started_at="2026-03-30T10:20:00Z",
            completed_at="2026-03-30T10:22:00Z",
            created_at="2026-03-30T10:19:00Z",
        )
        started_event = Event(
            id="event-1",
            run_id=run.id,
            task_id=task.id,
            project_id=project.id,
            event_type="agent.started",
            role_id="developer",
            timestamp="2026-03-30T10:20:00Z",
            payload={"session_id": run.session_id},
        )
        completion_event = Event(
            id="event-2",
            run_id=run.id,
            task_id=task.id,
            project_id=project.id,
            event_type="signal.completion",
            role_id="developer",
            timestamp="2026-03-30T10:22:00Z",
            payload={"summary": "Store slice completed."},
        )

        with ForemanStore(db_path) as store:
            store.initialize()
            store.initialize()
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)
            store.save_run(run)
            store.save_event(started_event)
            store.save_event(completion_event)

        with ForemanStore(db_path) as reopened:
            reopened.initialize()

            self.assertEqual(reopened.get_project(project.id), project)
            self.assertEqual(
                reopened.find_project_by_repo_path(project.repo_path),
                project,
            )
            self.assertEqual(reopened.list_projects(), [project])
            self.assertEqual(reopened.get_sprint(sprint.id), sprint)
            self.assertEqual(reopened.list_sprints(project.id), [sprint])
            self.assertEqual(reopened.get_active_sprint(project.id), sprint)
            self.assertEqual(reopened.get_task(task.id), task)
            self.assertEqual(reopened.list_tasks(project_id=project.id), [task])
            self.assertEqual(
                reopened.list_tasks(project_id=project.id, status="in_progress"),
                [task],
            )
            self.assertEqual(reopened.get_run(run.id), run)
            self.assertEqual(reopened.list_runs(task_id=task.id), [run])
            self.assertEqual(
                reopened.list_runs(task_id=task.id, status="completed"),
                [run],
            )
            self.assertEqual(reopened.get_latest_run(task.id), run)
            self.assertEqual(
                reopened.list_events(run_id=run.id),
                [started_event, completion_event],
            )
            self.assertEqual(
                reopened.task_counts(project.id),
                {
                    "todo": 0,
                    "in_progress": 1,
                    "blocked": 0,
                    "done": 0,
                    "cancelled": 0,
                },
            )

    def test_get_latest_session_id_uses_task_role_backend_scope(self) -> None:
        db_path = self.create_db_path()
        project = Project(
            id="project-1",
            name="Foreman",
            repo_path="/work/foreman",
            workflow_id="development",
            created_at="2026-03-30T10:00:00Z",
            updated_at="2026-03-30T10:00:00Z",
        )
        sprint = Sprint(
            id="sprint-1",
            project_id=project.id,
            title="Session reuse",
            status="active",
            created_at="2026-03-30T10:05:00Z",
            started_at="2026-03-30T10:10:00Z",
        )
        task = Task(
            id="task-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Reuse native sessions",
            status="in_progress",
            created_at="2026-03-30T10:15:00Z",
        )
        earlier_match = Run(
            id="run-1",
            task_id=task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude_code",
            status="completed",
            session_id="session-old",
            created_at="2026-03-30T10:20:00Z",
        )
        later_other_role = Run(
            id="run-2",
            task_id=task.id,
            project_id=project.id,
            role_id="code_reviewer",
            workflow_step="review",
            agent_backend="claude_code",
            status="completed",
            session_id="review-session",
            created_at="2026-03-30T10:25:00Z",
        )
        later_other_backend = Run(
            id="run-3",
            task_id=task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="codex",
            status="completed",
            session_id="codex-session",
            created_at="2026-03-30T10:30:00Z",
        )
        latest_match = Run(
            id="run-4",
            task_id=task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude_code",
            status="failed",
            session_id="session-new",
            created_at="2026-03-30T10:35:00Z",
        )
        empty_session = Run(
            id="run-5",
            task_id=task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude_code",
            status="completed",
            session_id=None,
            created_at="2026-03-30T10:40:00Z",
        )

        with ForemanStore(db_path) as store:
            store.initialize()
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)
            store.save_run(earlier_match)
            store.save_run(later_other_role)
            store.save_run(later_other_backend)
            store.save_run(latest_match)
            store.save_run(empty_session)

            self.assertEqual(
                store.get_latest_session_id(
                    task_id=task.id,
                    role_id="developer",
                    agent_backend="claude_code",
                ),
                "session-new",
            )
            self.assertEqual(
                store.get_latest_session_id(
                    task_id=task.id,
                    role_id="developer",
                    agent_backend="codex",
                ),
                "codex-session",
            )
            self.assertIsNone(
                store.get_latest_session_id(
                    task_id=task.id,
                    role_id="architect",
                    agent_backend="claude_code",
                ),
            )

    def test_only_one_active_sprint_is_allowed_per_project(self) -> None:
        db_path = self.create_db_path()
        project = Project(
            id="project-1",
            name="Foreman",
            repo_path="/work/foreman",
            workflow_id="development",
            created_at="2026-03-30T11:00:00Z",
            updated_at="2026-03-30T11:00:00Z",
        )
        active_one = Sprint(
            id="sprint-1",
            project_id=project.id,
            title="Sprint 1",
            status="active",
            created_at="2026-03-30T11:05:00Z",
            started_at="2026-03-30T11:10:00Z",
        )
        active_two = Sprint(
            id="sprint-2",
            project_id=project.id,
            title="Sprint 2",
            status="active",
            created_at="2026-03-30T11:15:00Z",
            started_at="2026-03-30T11:20:00Z",
        )

        with ForemanStore(db_path) as store:
            store.initialize()
            store.save_project(project)
            store.save_sprint(active_one)

            with self.assertRaises(sqlite3.IntegrityError):
                store.save_sprint(active_two)

    def test_monitoring_queries_scope_costs_and_recent_events(self) -> None:
        db_path = self.create_db_path()
        project = Project(
            id="project-1",
            name="Foreman",
            repo_path="/work/foreman",
            workflow_id="development",
            created_at="2026-03-30T11:00:00Z",
            updated_at="2026-03-30T11:00:00Z",
        )
        active_sprint = Sprint(
            id="sprint-1",
            project_id=project.id,
            title="Monitoring",
            status="active",
            order_index=2,
            created_at="2026-03-30T11:05:00Z",
            started_at="2026-03-30T11:06:00Z",
        )
        previous_sprint = Sprint(
            id="sprint-0",
            project_id=project.id,
            title="Previous",
            status="completed",
            order_index=1,
            created_at="2026-03-20T11:05:00Z",
            completed_at="2026-03-21T11:06:00Z",
        )
        active_task = Task(
            id="task-1",
            sprint_id=active_sprint.id,
            project_id=project.id,
            title="Active task",
            status="in_progress",
            created_at="2026-03-30T11:10:00Z",
        )
        idle_task = Task(
            id="task-2",
            sprint_id=active_sprint.id,
            project_id=project.id,
            title="Idle task",
            status="todo",
            created_at="2026-03-30T11:11:00Z",
        )
        previous_task = Task(
            id="task-3",
            sprint_id=previous_sprint.id,
            project_id=project.id,
            title="Previous task",
            status="done",
            created_at="2026-03-20T11:10:00Z",
        )
        active_run = Run(
            id="run-1",
            task_id=active_task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude_code",
            status="completed",
            cost_usd=1.50,
            token_count=100,
            duration_ms=2000,
            created_at="2026-03-30T11:20:00Z",
        )
        zero_cost_run = Run(
            id="run-2",
            task_id=active_task.id,
            project_id=project.id,
            role_id="code_reviewer",
            workflow_step="review",
            agent_backend="codex",
            status="completed",
            cost_usd=0.0,
            token_count=50,
            duration_ms=500,
            created_at="2026-03-30T11:25:00Z",
        )
        previous_run = Run(
            id="run-3",
            task_id=previous_task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude_code",
            status="completed",
            cost_usd=4.00,
            token_count=200,
            duration_ms=1000,
            created_at="2026-03-21T11:20:00Z",
        )
        first_event = Event(
            id="event-1",
            run_id=active_run.id,
            task_id=active_task.id,
            project_id=project.id,
            event_type="agent.message",
            timestamp="2026-03-30T11:21:00Z",
            payload={"text": "starting"},
        )
        second_event = Event(
            id="event-2",
            run_id=zero_cost_run.id,
            task_id=active_task.id,
            project_id=project.id,
            event_type="agent.command",
            timestamp="2026-03-30T11:22:00Z",
            payload={"command": "pytest"},
        )
        third_event = Event(
            id="event-3",
            run_id=zero_cost_run.id,
            task_id=active_task.id,
            project_id=project.id,
            event_type="signal.completion",
            timestamp="2026-03-30T11:23:00Z",
            payload={"summary": "done"},
        )

        with ForemanStore(db_path) as store:
            store.initialize()
            store.save_project(project)
            store.save_sprint(previous_sprint)
            store.save_sprint(active_sprint)
            store.save_task(active_task)
            store.save_task(idle_task)
            store.save_task(previous_task)
            store.save_run(active_run)
            store.save_run(zero_cost_run)
            store.save_run(previous_run)
            store.save_event(first_event)
            store.save_event(second_event)
            store.save_event(third_event)

            self.assertEqual(
                store.task_counts(sprint_id=active_sprint.id),
                {
                    "todo": 1,
                    "in_progress": 1,
                    "blocked": 0,
                    "done": 0,
                    "cancelled": 0,
                },
            )
            self.assertEqual(
                store.run_totals(project_id=project.id),
                {
                    "run_count": 3,
                    "total_cost_usd": 5.5,
                    "total_token_count": 350,
                    "total_duration_ms": 3500,
                    "zero_cost_token_runs": 1,
                },
            )
            self.assertEqual(
                store.run_totals(project_id=project.id, sprint_id=active_sprint.id),
                {
                    "run_count": 2,
                    "total_cost_usd": 1.5,
                    "total_token_count": 150,
                    "total_duration_ms": 2500,
                    "zero_cost_token_runs": 1,
                },
            )

            task_totals = {
                row["task_id"]: row for row in store.task_run_totals(sprint_id=active_sprint.id)
            }
            self.assertEqual(set(task_totals), {"task-1", "task-2"})
            self.assertEqual(task_totals["task-1"]["run_count"], 2)
            self.assertEqual(task_totals["task-1"]["total_cost_usd"], 1.5)
            self.assertEqual(task_totals["task-1"]["total_token_count"], 150)
            self.assertEqual(task_totals["task-2"]["run_count"], 0)
            self.assertEqual(task_totals["task-2"]["total_cost_usd"], 0.0)
            self.assertEqual(task_totals["task-2"]["total_token_count"], 0)

            self.assertEqual(
                store.list_recent_events(project_id=project.id, limit=2),
                [second_event, third_event],
            )

    def test_utc_now_text_preserves_microseconds(self) -> None:
        timestamp = utc_now_text()

        self.assertRegex(timestamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")

    def test_run_and_event_history_preserve_insertion_order_when_timestamps_match(self) -> None:
        db_path = self.create_db_path()
        project = Project(
            id="project-1",
            name="Foreman",
            repo_path="/work/foreman",
            workflow_id="development",
            created_at="2026-03-30T12:00:00.000000Z",
            updated_at="2026-03-30T12:00:00.000000Z",
        )
        sprint = Sprint(
            id="sprint-1",
            project_id=project.id,
            title="Ordering",
            status="active",
            created_at="2026-03-30T12:01:00.000000Z",
            started_at="2026-03-30T12:01:00.000000Z",
        )
        task = Task(
            id="task-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Preserve run ordering",
            status="in_progress",
            created_at="2026-03-30T12:02:00.000000Z",
        )
        first_run = Run(
            id="run-z",
            task_id=task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="codex",
            status="completed",
            outcome="done",
            created_at="2026-03-30T12:03:00.000000Z",
        )
        second_run = Run(
            id="run-a",
            task_id=task.id,
            project_id=project.id,
            role_id="code_reviewer",
            workflow_step="review",
            agent_backend="codex",
            status="completed",
            outcome="approve",
            created_at="2026-03-30T12:03:00.000000Z",
        )
        first_event = Event(
            id="event-z",
            run_id=first_run.id,
            task_id=task.id,
            project_id=project.id,
            event_type="workflow.step_started",
            timestamp="2026-03-30T12:04:00.000000Z",
            payload={"step": "develop"},
        )
        second_event = Event(
            id="event-a",
            run_id=second_run.id,
            task_id=task.id,
            project_id=project.id,
            event_type="workflow.step_completed",
            timestamp="2026-03-30T12:04:00.000000Z",
            payload={"step": "review"},
        )

        with ForemanStore(db_path) as store:
            store.initialize()
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)
            store.save_run(first_run)
            store.save_run(second_run)
            store.save_event(first_event)
            store.save_event(second_event)

            self.assertEqual(store.list_runs(task_id=task.id), [first_run, second_run])
            self.assertEqual(store.get_latest_run(task.id), second_run)
            self.assertEqual(
                store.list_events(task_id=task.id),
                [first_event, second_event],
            )


if __name__ == "__main__":
    unittest.main()
