"""Tests for runtime context projection."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from foreman.context import build_project_context, write_project_context
from foreman.models import Project, Sprint, Task
from foreman.store import ForemanStore


class ContextProjectionTests(unittest.TestCase):
    """Verify that runtime context is projected from persisted SQLite state."""

    def create_workspace(self) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo_path = root / "repo"
        repo_path.mkdir()
        db_path = root / "foreman.db"
        return repo_path, db_path

    def test_build_project_context_renders_active_sprint_current_task_and_summaries(self) -> None:
        repo_path, db_path = self.create_workspace()

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                workflow_id="development",
                default_branch="main",
                settings={"context_dir": ".foreman"},
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            completed_sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Foundation",
                goal="Land the first slice",
                status="completed",
                order_index=1,
                created_at="2026-03-30T12:05:00Z",
                started_at="2026-03-30T12:06:00Z",
                completed_at="2026-03-30T12:20:00Z",
            )
            active_sprint = Sprint(
                id="sprint-2",
                project_id=project.id,
                title="Context Projection",
                goal="Project runtime context",
                status="active",
                order_index=2,
                created_at="2026-03-30T12:25:00Z",
                started_at="2026-03-30T12:26:00Z",
            )
            completed_task = Task(
                id="task-1",
                sprint_id=completed_sprint.id,
                project_id=project.id,
                title="Add store baseline",
                status="done",
                created_at="2026-03-30T12:10:00Z",
                completed_at="2026-03-30T12:18:00Z",
            )
            active_task = Task(
                id="task-2",
                sprint_id=active_sprint.id,
                project_id=project.id,
                title="Write context files",
                description="Project `.foreman` files from SQLite.",
                acceptance_criteria="Context files exist and reflect task state.",
                status="in_progress",
                task_type="feature",
                branch_name="feat/task-2-write-context-files",
                created_at="2026-03-30T12:30:00Z",
            )
            blocked_task = Task(
                id="task-3",
                sprint_id=active_sprint.id,
                project_id=project.id,
                title="Resolve projection ambiguity",
                status="blocked",
                blocked_reason="Need schema clarification.",
                created_at="2026-03-30T12:31:00Z",
            )
            store.save_project(project)
            store.save_sprint(completed_sprint)
            store.save_sprint(active_sprint)
            store.save_task(completed_task)
            store.save_task(active_task)
            store.save_task(blocked_task)

            projection = build_project_context(
                store,
                project,
                current_task=active_task,
                carried_output="Carry the prior reviewer note forward.",
            )

        self.assertEqual(projection.context_path, repo_path / ".foreman" / "context.md")
        self.assertEqual(projection.status_path, repo_path / ".foreman" / "status.md")
        self.assertIn("# Sprint Context", projection.context_markdown)
        self.assertIn("Sprint: Context Projection", projection.context_markdown)
        self.assertIn("* [in_progress] Write context files (task-2)", projection.context_markdown)
        self.assertIn("### Description", projection.context_markdown)
        self.assertIn("Project `.foreman` files from SQLite.", projection.context_markdown)
        self.assertIn("Carry the prior reviewer note forward.", projection.context_markdown)

        self.assertIn("# Project Status", projection.status_markdown)
        self.assertIn("- [completed] Foundation (sprint-1)", projection.status_markdown)
        self.assertIn("### Foundation", projection.status_markdown)
        self.assertIn("- Add store baseline", projection.status_markdown)
        self.assertIn(
            "- Resolve projection ambiguity (task-3): Need schema clarification.",
            projection.status_markdown,
        )
        self.assertIn("- Not yet persisted in SQLite.", projection.status_markdown)

    def test_write_project_context_writes_files_to_the_configured_runtime_directory(self) -> None:
        repo_path, db_path = self.create_workspace()

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=str(repo_path),
                workflow_id="development",
                settings={"context_dir": ".foreman/runtime"},
                created_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:00:00Z",
            )
            sprint = Sprint(
                id="sprint-1",
                project_id=project.id,
                title="Context Projection",
                status="active",
                created_at="2026-03-30T12:05:00Z",
                started_at="2026-03-30T12:06:00Z",
            )
            task = Task(
                id="task-1",
                sprint_id=sprint.id,
                project_id=project.id,
                title="Write context",
                status="in_progress",
                created_at="2026-03-30T12:10:00Z",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            store.save_task(task)

            projection = write_project_context(store, project, current_task=task)

        self.assertTrue(projection.context_path.is_file())
        self.assertTrue(projection.status_path.is_file())
        self.assertEqual(
            projection.context_path.read_text(encoding="utf-8"),
            projection.context_markdown,
        )
        self.assertEqual(
            projection.status_path.read_text(encoding="utf-8"),
            projection.status_markdown,
        )


if __name__ == "__main__":
    unittest.main()
