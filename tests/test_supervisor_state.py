"""Regression tests for supervisor-to-SQLite completion reconciliation."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from foreman.models import Project, Sprint, Task
from foreman.store import ForemanStore
from foreman.supervisor_state import finalize_supervisor_merge


class SupervisorStateTests(unittest.TestCase):
    def create_db_path(self) -> str:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return str(Path(temp_dir.name) / "foreman.db")

    def test_finalize_supervisor_merge_marks_task_done_and_completes_active_sprint(self) -> None:
        db_path = self.create_db_path()
        repo_path = "/work/foreman"
        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman",
                repo_path=repo_path,
                workflow_id="development",
                autonomy_level="supervised",
                created_at="2026-04-22T10:00:00Z",
                updated_at="2026-04-22T10:00:00Z",
            )
            sprint = Sprint(
                id="sprint-44",
                project_id=project.id,
                title="Supervisor state reconciliation",
                status="active",
                created_at="2026-04-22T10:01:00Z",
                started_at="2026-04-22T10:02:00Z",
            )
            next_sprint = Sprint(
                id="sprint-45",
                project_id=project.id,
                title="Next sprint",
                status="planned",
                order_index=1,
                created_at="2026-04-22T10:03:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Finalize reviewed merge",
                status="blocked",
                branch_name="feat/task-1",
                blocked_reason="Awaiting review resolution",
                created_at="2026-04-22T10:04:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_sprint(next_sprint)
            store.save_task(task)

            result = finalize_supervisor_merge(
                store,
                repo_path=repo_path,
                branch_name="feat/task-1",
                utc_now=lambda: datetime(2026, 4, 22, 10, 5, tzinfo=timezone.utc),
            )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.task_id, task.id)
            self.assertEqual(result.task_status, "done")
            self.assertEqual(result.sprint_status, "completed")
            self.assertEqual(result.stop_reason, "sprint_complete")

            refreshed_task = store.get_task(task.id)
            assert refreshed_task is not None
            self.assertEqual(refreshed_task.status, "done")
            self.assertIsNone(refreshed_task.blocked_reason)
            self.assertIsNotNone(refreshed_task.completed_at)

            refreshed_sprint = store.get_sprint(sprint.id)
            assert refreshed_sprint is not None
            self.assertEqual(refreshed_sprint.status, "completed")
            self.assertIsNotNone(refreshed_sprint.completed_at)

            upcoming = store.get_sprint(next_sprint.id)
            assert upcoming is not None
            self.assertEqual(upcoming.status, "planned")

            events = store.list_events(task_id=task.id)
            self.assertIn("engine.supervisor_merge", [event.event_type for event in events])
            self.assertIn("engine.sprint_completed", [event.event_type for event in events])
            self.assertIn("engine.sprint_ready", [event.event_type for event in events])

    def test_finalize_supervisor_merge_returns_none_when_branch_is_unknown(self) -> None:
        db_path = self.create_db_path()
        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman",
                repo_path="/work/foreman",
                workflow_id="development",
            )
            store.save_project(project)

            result = finalize_supervisor_merge(
                store,
                repo_path=project.repo_path,
                branch_name="feat/missing",
            )

            self.assertIsNone(result)

    def test_finalize_supervisor_merge_prefers_explicit_task_id(self) -> None:
        db_path = self.create_db_path()
        repo_path = "/work/foreman"
        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman",
                repo_path=repo_path,
                workflow_id="development",
            )
            sprint = Sprint(
                id="sprint-44",
                project_id=project.id,
                title="Supervisor state reconciliation",
                status="active",
            )
            task = Task(
                id="sprint-44-t2",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Explicit identity finalization",
                status="blocked",
                branch_name="feat/mismatched-branch",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)

            result = finalize_supervisor_merge(
                store,
                repo_path=repo_path,
                branch_name="feat/other-branch",
                task_id=task.id,
                utc_now=lambda: datetime(2026, 4, 22, 11, 0, tzinfo=timezone.utc),
            )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.task_id, task.id)
            refreshed_task = store.get_task(task.id)
            assert refreshed_task is not None
            self.assertEqual(refreshed_task.status, "done")

    def test_finalize_supervisor_merge_skips_already_done_task(self) -> None:
        """When the task is already done, no new events or state changes are emitted."""
        db_path = self.create_db_path()
        repo_path = "/work/foreman"
        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman",
                repo_path=repo_path,
                workflow_id="development",
            )
            sprint = Sprint(
                id="sprint-44",
                project_id=project.id,
                title="Test sprint",
                status="active",
            )
            done_task = Task(
                id="task-done",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Already done task",
                status="done",
                branch_name="feat/task-done",
                completed_at="2026-04-22T10:00:00Z",
            )
            open_task = Task(
                id="task-open",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Still running",
                status="in_progress",
                branch_name="feat/task-open",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(done_task)
            store.save_task(open_task)

            result = finalize_supervisor_merge(
                store,
                repo_path=repo_path,
                branch_name="feat/task-done",
            )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.task_id, done_task.id)
            self.assertEqual(result.task_status, "done")
            # Sprint must still be active — not all tasks resolved
            self.assertEqual(result.sprint_status, "active")
            self.assertIsNone(result.stop_reason)

            # No new engine.supervisor_merge event for already-done task
            events = store.list_events(task_id=done_task.id)
            event_types = [e.event_type for e in events]
            self.assertNotIn("engine.supervisor_merge", event_types)

    def test_finalize_supervisor_merge_does_not_complete_sprint_when_other_tasks_unresolved(self) -> None:
        """Completing one task does not close the sprint if another task remains open."""
        db_path = self.create_db_path()
        repo_path = "/work/foreman"
        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman",
                repo_path=repo_path,
                workflow_id="development",
            )
            sprint = Sprint(
                id="sprint-44",
                project_id=project.id,
                title="Multi-task sprint",
                status="active",
            )
            done_task = Task(
                id="task-done",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Already done",
                status="done",
                branch_name="feat/done",
            )
            open_task = Task(
                id="task-open",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Still in progress",
                status="in_progress",
                branch_name="feat/open",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(done_task)
            store.save_task(open_task)

            result = finalize_supervisor_merge(
                store,
                repo_path=repo_path,
                branch_name="feat/done",
            )

            self.assertIsNotNone(result)
            assert result is not None
            # Sprint should NOT be completed — task-open is still in_progress
            self.assertEqual(result.sprint_status, "active")
            self.assertIsNone(result.stop_reason)

            refreshed_sprint = store.get_sprint(sprint.id)
            assert refreshed_sprint is not None
            self.assertEqual(refreshed_sprint.status, "active")

    def test_finalize_supervisor_merge_rejects_task_id_from_other_project(self) -> None:
        db_path = self.create_db_path()
        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman",
                repo_path="/work/foreman",
                workflow_id="development",
            )
            other_project = Project(
                id="project-2",
                name="Other",
                repo_path="/work/other",
                workflow_id="development",
            )
            sprint = Sprint(id="sprint-1", project_id=other_project.id, title="Other sprint", status="active")
            task = Task(
                id="task-other",
                sprint_id=sprint.id,
                project_id=other_project.id,
                title="Other project task",
                status="blocked",
                branch_name="feat/task-other",
            )
            store.save_project(project)
            store.save_project(other_project)
            store.save_sprint(sprint)
            store.save_task(task)

            result = finalize_supervisor_merge(
                store,
                repo_path=project.repo_path,
                branch_name="feat/task-other",
                task_id=task.id,
            )

            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
