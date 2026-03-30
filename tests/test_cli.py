"""Smoke tests for the Foreman CLI foundation slices."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.models import Project, Sprint, Task
from foreman.store import ForemanStore

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_BIN = REPO_ROOT / "venv" / "bin"
PIP = VENV_BIN / "pip"
FOREMAN = VENV_BIN / "foreman"


class ForemanCLISmokeTests(unittest.TestCase):
    """Verify that the initial CLI shell is wired and runnable."""

    @classmethod
    def setUpClass(cls) -> None:
        install_result = subprocess.run(
            [
                str(PIP),
                "install",
                "-e",
                ".",
                "--no-build-isolation",
                "--no-deps",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if install_result.returncode != 0:
            raise AssertionError(
                "Editable install failed:\n"
                f"stdout:\n{install_result.stdout}\n"
                f"stderr:\n{install_result.stderr}"
            )
        if not FOREMAN.is_file():
            raise AssertionError(f"Console entrypoint was not created at {FOREMAN}")

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(FOREMAN), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def create_store(self) -> tuple[ForemanStore, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "foreman.db"
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()
        return store, db_path

    def test_help_lists_bootstrap_commands(self) -> None:
        result = self.run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: foreman", result.stdout)
        self.assertIn("projects", result.stdout)
        self.assertIn("status", result.stdout)
        self.assertIn("init", result.stdout)

    def test_projects_command_reports_empty_bootstrap_state(self) -> None:
        result = self.run_cli("projects")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Projects", result.stdout)
        self.assertIn("No projects are tracked yet.", result.stdout)
        self.assertIn("SQLite-backed inspection is available now via `--db PATH`", result.stdout)

    def test_status_command_reports_empty_bootstrap_state(self) -> None:
        result = self.run_cli("status")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Status", result.stdout)
        self.assertIn("No active projects or sprints.", result.stdout)
        self.assertIn("SQLite-backed inspection is available now via `--db PATH`", result.stdout)

    def test_projects_command_can_read_store_with_db_path(self) -> None:
        store, db_path = self.create_store()
        project = Project(
            id="project-1",
            name="Foreman Demo",
            repo_path="/tmp/foreman-demo",
            workflow_id="development",
            created_at="2026-03-30T09:00:00Z",
            updated_at="2026-03-30T09:00:00Z",
        )
        sprint = Sprint(
            id="sprint-1",
            project_id=project.id,
            title="Sprint 1",
            goal="Bootstrap persistence",
            status="active",
            order_index=1,
            created_at="2026-03-30T09:05:00Z",
            started_at="2026-03-30T09:10:00Z",
        )
        task = Task(
            id="task-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Persist projects",
            status="in_progress",
            created_at="2026-03-30T09:15:00Z",
        )
        store.save_project(project)
        store.save_sprint(sprint)
        store.save_task(task)

        result = self.run_cli("projects", "--db", str(db_path))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Database: {db_path}", result.stdout)
        self.assertIn("project-1 | Foreman Demo | workflow=development | active_sprint=Sprint 1", result.stdout)
        self.assertIn("repo=/tmp/foreman-demo | todo=0 in_progress=1 blocked=0 done=0 cancelled=0", result.stdout)

    def test_status_command_can_read_store_with_db_path(self) -> None:
        store, db_path = self.create_store()
        project = Project(
            id="project-1",
            name="Foreman Demo",
            repo_path="/tmp/foreman-demo",
            workflow_id="development",
            created_at="2026-03-30T09:00:00Z",
            updated_at="2026-03-30T09:00:00Z",
        )
        active_sprint = Sprint(
            id="sprint-1",
            project_id=project.id,
            title="Sprint 1",
            status="active",
            created_at="2026-03-30T09:05:00Z",
            started_at="2026-03-30T09:10:00Z",
        )
        done_sprint = Sprint(
            id="sprint-2",
            project_id=project.id,
            title="Sprint 0",
            status="completed",
            order_index=2,
            created_at="2026-03-20T09:05:00Z",
            completed_at="2026-03-21T09:10:00Z",
        )
        store.save_project(project)
        store.save_sprint(active_sprint)
        store.save_sprint(done_sprint)
        store.save_task(
            Task(
                id="task-1",
                sprint_id=active_sprint.id,
                project_id=project.id,
                title="Todo task",
                status="todo",
                created_at="2026-03-30T09:15:00Z",
            )
        )
        store.save_task(
            Task(
                id="task-2",
                sprint_id=active_sprint.id,
                project_id=project.id,
                title="Done task",
                status="done",
                created_at="2026-03-30T09:16:00Z",
            )
        )

        result = self.run_cli("status", "--db", str(db_path))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Database: {db_path}", result.stdout)
        self.assertIn("Projects: 1", result.stdout)
        self.assertIn("Active sprints: 1", result.stdout)
        self.assertIn("Tasks: todo=1 in_progress=0 blocked=0 done=1 cancelled=0", result.stdout)

    def test_roles_command_lists_shipped_roles(self) -> None:
        result = self.run_cli("roles")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Roles", result.stdout)
        self.assertIn("developer | backend=claude_code | model=project-default | session=persistent", result.stdout)
        self.assertIn("code_reviewer | backend=claude_code | model=claude-sonnet-4-6 | session=ephemeral", result.stdout)

    def test_workflows_command_lists_shipped_workflows(self) -> None:
        result = self.run_cli("workflows")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Workflows", result.stdout)
        self.assertIn("development | methodology=development | entry=develop | steps=5 | transitions=8 | gates=2 | fallback=block", result.stdout)
        self.assertIn("development_secure | methodology=development | entry=develop | steps=6 | transitions=10 | gates=1 | fallback=block", result.stdout)


if __name__ == "__main__":
    unittest.main()
