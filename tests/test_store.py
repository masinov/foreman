"""Round-trip tests for the SQLite-backed Foreman store."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from foreman.models import Event, Project, Run, Sprint, Task
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


if __name__ == "__main__":
    unittest.main()
