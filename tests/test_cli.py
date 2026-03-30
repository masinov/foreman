"""Smoke tests for the Foreman CLI foundation slices."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.models import Event, Project, Run, Sprint, Task
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

    def seed_monitoring_state(self, store: ForemanStore) -> dict[str, str]:
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
            title="Monitoring Sprint",
            goal="Ship monitoring surfaces",
            status="active",
            order_index=2,
            created_at="2026-03-30T09:05:00Z",
            started_at="2026-03-30T09:10:00Z",
        )
        previous_sprint = Sprint(
            id="sprint-0",
            project_id=project.id,
            title="Runner Sprint",
            goal="Land native runners",
            status="completed",
            order_index=1,
            created_at="2026-03-20T09:05:00Z",
            started_at="2026-03-20T09:10:00Z",
            completed_at="2026-03-21T10:00:00Z",
        )
        todo_task = Task(
            id="task-todo",
            sprint_id=active_sprint.id,
            project_id=project.id,
            title="Queue board column",
            status="todo",
            task_type="feature",
            created_at="2026-03-30T09:15:00Z",
        )
        wip_task = Task(
            id="task-wip",
            sprint_id=active_sprint.id,
            project_id=project.id,
            title="Render activity feed",
            status="in_progress",
            task_type="feature",
            branch_name="feat/render-activity-feed",
            assigned_role="developer",
            workflow_current_step="develop",
            step_visit_counts={"develop": 2, "review": 1},
            created_at="2026-03-30T09:16:00Z",
            started_at="2026-03-30T09:17:00Z",
        )
        blocked_task = Task(
            id="task-blocked",
            sprint_id=active_sprint.id,
            project_id=project.id,
            title="Approve polling UX",
            status="blocked",
            task_type="docs",
            branch_name="feat/approve-polling-ux",
            assigned_role="architect",
            blocked_reason="Awaiting human approval",
            workflow_current_step="human_approval",
            created_at="2026-03-30T09:18:00Z",
            started_at="2026-03-30T09:19:00Z",
        )
        done_task = Task(
            id="task-done",
            sprint_id=active_sprint.id,
            project_id=project.id,
            title="Land store summaries",
            status="done",
            task_type="refactor",
            branch_name="feat/store-summaries",
            created_at="2026-03-30T09:20:00Z",
            completed_at="2026-03-30T10:00:00Z",
        )
        old_task = Task(
            id="task-old",
            sprint_id=previous_sprint.id,
            project_id=project.id,
            title="Ship Codex backend",
            status="done",
            task_type="feature",
            branch_name="feat/codex-runner",
            created_at="2026-03-20T09:20:00Z",
            completed_at="2026-03-21T09:55:00Z",
        )
        runs = [
            Run(
                id="run-wip-1",
                task_id=wip_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="codex",
                status="completed",
                outcome="done",
                outcome_detail="Initial implementation landed.",
                model="gpt-5.4",
                session_id="thread-1",
                branch_name=wip_task.branch_name,
                cost_usd=0.0,
                token_count=610,
                duration_ms=3000,
                created_at="2026-03-30T09:30:00Z",
                started_at="2026-03-30T09:30:00Z",
                completed_at="2026-03-30T09:33:00Z",
            ),
            Run(
                id="run-wip-2",
                task_id=wip_task.id,
                project_id=project.id,
                role_id="code_reviewer",
                workflow_step="review",
                agent_backend="claude_code",
                status="completed",
                outcome="revise",
                outcome_detail="Add more activity detail.",
                model="claude-sonnet-4-6",
                session_id="session-2",
                branch_name=wip_task.branch_name,
                cost_usd=1.25,
                token_count=300,
                duration_ms=1200,
                created_at="2026-03-30T09:40:00Z",
                started_at="2026-03-30T09:40:00Z",
                completed_at="2026-03-30T09:41:12Z",
            ),
            Run(
                id="run-done-1",
                task_id=done_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="completed",
                outcome="done",
                outcome_detail="Store summaries are complete.",
                model="claude-sonnet-4-6",
                session_id="session-3",
                branch_name=done_task.branch_name,
                cost_usd=0.75,
                token_count=240,
                duration_ms=900,
                created_at="2026-03-30T09:50:00Z",
                started_at="2026-03-30T09:50:00Z",
                completed_at="2026-03-30T09:51:30Z",
            ),
            Run(
                id="run-old-1",
                task_id=old_task.id,
                project_id=project.id,
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="completed",
                outcome="done",
                model="claude-sonnet-4-6",
                session_id="session-old",
                branch_name=old_task.branch_name,
                cost_usd=5.00,
                token_count=999,
                duration_ms=5000,
                created_at="2026-03-21T09:30:00Z",
                started_at="2026-03-21T09:30:00Z",
                completed_at="2026-03-21T09:35:00Z",
            ),
        ]
        events = [
            Event(
                id="event-wip-1",
                run_id="run-wip-1",
                task_id=wip_task.id,
                project_id=project.id,
                event_type="agent.message",
                role_id="developer",
                timestamp="2026-03-30T09:31:00Z",
                payload={"text": "Implementing board renderer"},
            ),
            Event(
                id="event-wip-2",
                run_id="run-wip-1",
                task_id=wip_task.id,
                project_id=project.id,
                event_type="agent.command",
                role_id="developer",
                timestamp="2026-03-30T09:31:30Z",
                payload={"command": "./venv/bin/python -m unittest tests.test_cli"},
            ),
            Event(
                id="event-wip-3",
                run_id="run-wip-1",
                task_id=wip_task.id,
                project_id=project.id,
                event_type="agent.file_change",
                role_id="developer",
                timestamp="2026-03-30T09:32:00Z",
                payload={"path": "foreman/cli.py"},
            ),
            Event(
                id="event-wip-4",
                run_id="run-wip-2",
                task_id=wip_task.id,
                project_id=project.id,
                event_type="signal.completion",
                role_id="code_reviewer",
                timestamp="2026-03-30T09:41:12Z",
                payload={"summary": "Add more activity detail."},
            ),
            Event(
                id="event-done-1",
                run_id="run-done-1",
                task_id=done_task.id,
                project_id=project.id,
                event_type="signal.completion",
                role_id="developer",
                timestamp="2026-03-30T09:51:30Z",
                payload={"summary": "Store summaries are complete."},
            ),
            Event(
                id="event-old-1",
                run_id="run-old-1",
                task_id=old_task.id,
                project_id=project.id,
                event_type="signal.completion",
                role_id="developer",
                timestamp="2026-03-21T09:35:00Z",
                payload={"summary": "Codex runner shipped."},
            ),
        ]

        store.save_project(project)
        store.save_sprint(previous_sprint)
        store.save_sprint(active_sprint)
        for task in (todo_task, wip_task, blocked_task, done_task, old_task):
            store.save_task(task)
        for run in runs:
            store.save_run(run)
        for event in events:
            store.save_event(event)
        return {
            "project_id": project.id,
            "active_sprint_id": active_sprint.id,
            "wip_task_id": wip_task.id,
            "wip_run_id": "run-wip-1",
        }

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
        self.assertIn("Project creation is available via `foreman init --db PATH`", result.stdout)

    def test_status_command_reports_empty_bootstrap_state(self) -> None:
        result = self.run_cli("status")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Status", result.stdout)
        self.assertIn("No active projects or sprints.", result.stdout)
        self.assertIn("SQLite-backed inspection is available now via `--db PATH`", result.stdout)
        self.assertIn("Project creation is available via `foreman init --db PATH`", result.stdout)

    def test_init_command_scaffolds_repo_and_persists_project_with_db_path(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_path = Path(temp_dir.name) / "target-repo"
        repo_path.mkdir()
        spec_path = repo_path / "docs" / "spec.md"
        spec_path.parent.mkdir(parents=True)
        spec_path.write_text("# Spec\n", encoding="utf-8")
        db_path = Path(temp_dir.name) / "foreman.db"

        result = self.run_cli(
            "init",
            str(repo_path),
            "--name",
            "Sample Project",
            "--spec",
            "docs/spec.md",
            "--workflow",
            "development",
            "--db",
            str(db_path),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Initialized project", result.stdout)
        self.assertIn(f"Database: {db_path}", result.stdout)
        self.assertIn("Project ID: sample-project", result.stdout)
        self.assertIn("AGENTS.md | created", result.stdout)
        self.assertIn("docs/adr/ | created", result.stdout)
        self.assertIn(".foreman/ | created", result.stdout)
        self.assertIn(".gitignore | created", result.stdout)
        self.assertTrue((repo_path / "AGENTS.md").is_file())
        self.assertTrue((repo_path / "docs" / "adr").is_dir())
        self.assertTrue((repo_path / ".foreman").is_dir())
        self.assertEqual((repo_path / ".gitignore").read_text(encoding="utf-8"), ".foreman/\n")
        self.assertIn("Project: Sample Project", (repo_path / "AGENTS.md").read_text(encoding="utf-8"))

        with ForemanStore(db_path) as store:
            store.initialize()
            project = store.find_project_by_repo_path(str(repo_path))

        self.assertIsNotNone(project)
        assert project is not None
        self.assertEqual(project.id, "sample-project")
        self.assertEqual(project.spec_path, "docs/spec.md")
        self.assertEqual(project.workflow_id, "development")
        self.assertEqual(project.default_branch, "main")
        self.assertEqual(project.settings["context_dir"], ".foreman")
        self.assertEqual(
            project.settings["test_command"],
            "./venv/bin/python -m unittest discover -s tests",
        )

    def test_init_command_preserves_existing_agents_and_updates_existing_project(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_path = Path(temp_dir.name) / "target-repo"
        repo_path.mkdir()
        spec_path = repo_path / "docs" / "spec.md"
        spec_path.parent.mkdir(parents=True)
        spec_path.write_text("# Spec\n", encoding="utf-8")
        (repo_path / "AGENTS.md").write_text("# Custom Instructions\n", encoding="utf-8")
        db_path = Path(temp_dir.name) / "foreman.db"

        first = self.run_cli(
            "init",
            str(repo_path),
            "--name",
            "Sample Project",
            "--spec",
            "docs/spec.md",
            "--db",
            str(db_path),
        )
        second = self.run_cli(
            "init",
            str(repo_path),
            "--name",
            "Sample Project Renamed",
            "--spec",
            "docs/spec.md",
            "--workflow",
            "development_with_architect",
            "--default-branch",
            "trunk",
            "--test-command",
            "pytest -q",
            "--db",
            str(db_path),
        )

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Updated project", second.stdout)
        self.assertIn("AGENTS.md | unchanged", second.stdout)
        self.assertIn(".gitignore | unchanged", second.stdout)
        self.assertEqual((repo_path / "AGENTS.md").read_text(encoding="utf-8"), "# Custom Instructions\n")

        with ForemanStore(db_path) as store:
            store.initialize()
            projects = store.list_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].id, "sample-project")
        self.assertEqual(projects[0].name, "Sample Project Renamed")
        self.assertEqual(projects[0].workflow_id, "development_with_architect")
        self.assertEqual(projects[0].default_branch, "trunk")
        self.assertEqual(projects[0].settings["test_command"], "pytest -q")

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

    def test_board_command_shows_active_sprint_tasks_grouped_by_status(self) -> None:
        store, db_path = self.create_store()
        fixture = self.seed_monitoring_state(store)

        result = self.run_cli("board", fixture["project_id"], "--db", str(db_path))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Board", result.stdout)
        self.assertIn(f"Database: {db_path}", result.stdout)
        self.assertIn("Sprint: sprint-1 | Monitoring Sprint", result.stdout)
        self.assertIn("Progress: done=1/4 | in_progress=1 | blocked=1 | todo=1 | cancelled=0", result.stdout)
        self.assertIn("Activity: runs=3 | tokens=1150 | cost_usd=$2.00", result.stdout)
        self.assertIn("Todo (1)", result.stdout)
        self.assertIn("- task-todo | feature | Queue board column", result.stdout)
        self.assertIn("In Progress (1)", result.stdout)
        self.assertIn(
            "- task-wip | feature | Render activity feed | tokens=910 | branch=feat/render-activity-feed | role=developer | step=develop | visits=develop=2, review=1",
            result.stdout,
        )
        self.assertIn("Blocked (1)", result.stdout)
        self.assertIn("reason=Awaiting human approval", result.stdout)
        self.assertIn("Done (1)", result.stdout)
        self.assertIn("task-done | refactor | Land store summaries", result.stdout)

    def test_history_command_shows_runs_and_events_for_one_task(self) -> None:
        store, db_path = self.create_store()
        fixture = self.seed_monitoring_state(store)

        result = self.run_cli("history", fixture["wip_task_id"], "--db", str(db_path))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("History", result.stdout)
        self.assertIn(f"Task: {fixture['wip_task_id']} | Render activity feed", result.stdout)
        self.assertIn("Totals: runs=2 | tokens=910 | cost_usd=$1.25 | duration_ms=4200", result.stdout)
        self.assertIn("Step visits: develop=2, review=1", result.stdout)
        self.assertIn("Runs:", result.stdout)
        self.assertIn(
            "- run-wip-1 | role=developer | step=develop | backend=codex | status=completed | cost_usd=$0.00 | tokens=610 | duration_ms=3000 | retries=0 | outcome=done | detail=Initial implementation landed. | model=gpt-5.4 | session=thread-1",
            result.stdout,
        )
        self.assertIn("Events:", result.stdout)
        self.assertIn(
            "- 2026-03-30T09:31:30Z | agent.command | role=developer | ./venv/bin/python -m unittest tests.test_cli",
            result.stdout,
        )
        self.assertIn(
            "- 2026-03-30T09:41:12Z | signal.completion | role=code_reviewer | summary=Add more activity detail.",
            result.stdout,
        )

    def test_cost_command_can_scope_to_the_active_sprint(self) -> None:
        store, db_path = self.create_store()
        fixture = self.seed_monitoring_state(store)

        result = self.run_cli(
            "cost",
            fixture["project_id"],
            "--sprint",
            fixture["active_sprint_id"],
            "--db",
            str(db_path),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Cost", result.stdout)
        self.assertIn("Scope: sprint sprint-1 | Monitoring Sprint", result.stdout)
        self.assertIn("Totals: runs=3 | tokens=1150 | cost_usd=$2.00 | duration_ms=5100", result.stdout)
        self.assertIn(
            "- task-wip | feature | Render activity feed | status=in_progress | runs=2 | tokens=910 | cost_usd=$1.25",
            result.stdout,
        )
        self.assertIn(
            "- task-todo | feature | Queue board column | status=todo | runs=0 | tokens=0 | cost_usd=$0.00",
            result.stdout,
        )
        self.assertNotIn("task-old", result.stdout)
        self.assertIn(
            "Note: some runs reported token usage with $0.00 cost; persisted USD totals do not infer missing backend pricing.",
            result.stdout,
        )

    def test_watch_command_shows_project_snapshot_without_mutating_state(self) -> None:
        store, db_path = self.create_store()
        fixture = self.seed_monitoring_state(store)

        result = self.run_cli(
            "watch",
            fixture["project_id"],
            "--db",
            str(db_path),
            "--iterations",
            "1",
            "--limit",
            "3",
            "--interval",
            "0",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Watch", result.stdout)
        self.assertIn("Scope: project project-1", result.stdout)
        self.assertIn("Snapshot 1/1 |", result.stdout)
        self.assertIn("Sprint: sprint-1 | Monitoring Sprint", result.stdout)
        self.assertIn("Tasks: todo=1 in_progress=1 blocked=1 done=1 cancelled=0", result.stdout)
        self.assertIn("Activity: runs=3 | tokens=1150 | cost_usd=$2.00", result.stdout)
        self.assertIn(
            "- 2026-03-30T09:41:12Z | signal.completion | role=code_reviewer | summary=Add more activity detail.",
            result.stdout,
        )

        refreshed = store.get_task(fixture["wip_task_id"])
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.status, "in_progress")

    def test_watch_command_can_scope_to_one_run(self) -> None:
        store, db_path = self.create_store()
        fixture = self.seed_monitoring_state(store)

        result = self.run_cli(
            "watch",
            "--run",
            fixture["wip_run_id"],
            "--db",
            str(db_path),
            "--iterations",
            "1",
            "--limit",
            "2",
            "--interval",
            "0",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Scope: run run-wip-1", result.stdout)
        self.assertIn("Task: task-wip | Render activity feed", result.stdout)
        self.assertIn("Run: status=completed | step=develop | role=developer", result.stdout)
        self.assertIn(
            "- 2026-03-30T09:31:30Z | agent.command | role=developer | ./venv/bin/python -m unittest tests.test_cli",
            result.stdout,
        )
        self.assertIn(
            "- 2026-03-30T09:32:00Z | agent.file_change | role=developer | foreman/cli.py",
            result.stdout,
        )

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

    def test_approve_command_records_a_deferred_resume_for_paused_human_gate_tasks(self) -> None:
        store, db_path = self.create_store()
        project = Project(
            id="project-1",
            name="Foreman Demo",
            repo_path="/tmp/foreman-demo",
            workflow_id="development_with_architect",
            default_branch="main",
            settings={"task_selection_mode": "directed"},
            created_at="2026-03-30T09:00:00Z",
            updated_at="2026-03-30T09:00:00Z",
        )
        sprint = Sprint(
            id="sprint-1",
            project_id=project.id,
            title="Sprint 1",
            goal="Resume paused work",
            status="active",
            order_index=1,
            created_at="2026-03-30T09:05:00Z",
            started_at="2026-03-30T09:10:00Z",
        )
        task = Task(
            id="task-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Approve the architect plan",
            status="blocked",
            task_type="feature",
            branch_name="feat/task-1-approve-the-architect-plan",
            blocked_reason="Awaiting human approval",
            workflow_current_step="human_approval",
            created_at="2026-03-30T09:15:00Z",
            started_at="2026-03-30T09:16:00Z",
        )
        store.save_project(project)
        store.save_sprint(sprint)
        store.save_task(task)

        result = self.run_cli("approve", "task-1", "--db", str(db_path))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Approved task", result.stdout)
        self.assertIn(f"Database: {db_path}", result.stdout)
        self.assertIn("Resume from: human_approval", result.stdout)
        self.assertIn("Next step: develop", result.stdout)
        self.assertIn("Status: in_progress", result.stdout)
        self.assertIn("Resume deferred: yes", result.stdout)
        self.assertIn("Persisted step: develop", result.stdout)

        refreshed = store.get_task(task.id)
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.status, "in_progress")
        self.assertEqual(refreshed.workflow_current_step, "develop")
        self.assertIsNone(refreshed.workflow_carried_output)
        self.assertIsNone(refreshed.blocked_reason)

    def test_deny_command_carries_the_note_into_the_deferred_resume_state(self) -> None:
        store, db_path = self.create_store()
        project = Project(
            id="project-1",
            name="Foreman Demo",
            repo_path="/tmp/foreman-demo",
            workflow_id="development_with_architect",
            default_branch="main",
            settings={"task_selection_mode": "directed"},
            created_at="2026-03-30T09:00:00Z",
            updated_at="2026-03-30T09:00:00Z",
        )
        sprint = Sprint(
            id="sprint-1",
            project_id=project.id,
            title="Sprint 1",
            goal="Resume paused work",
            status="active",
            order_index=1,
            created_at="2026-03-30T09:05:00Z",
            started_at="2026-03-30T09:10:00Z",
        )
        task = Task(
            id="task-1",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Rework the architect plan",
            status="blocked",
            task_type="feature",
            branch_name="feat/task-1-rework-the-architect-plan",
            blocked_reason="Awaiting human approval",
            workflow_current_step="human_approval",
            created_at="2026-03-30T09:15:00Z",
            started_at="2026-03-30T09:16:00Z",
        )
        store.save_project(project)
        store.save_sprint(sprint)
        store.save_task(task)

        result = self.run_cli(
            "deny",
            "task-1",
            "--note",
            "rethink the approach",
            "--db",
            str(db_path),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Denied task", result.stdout)
        self.assertIn("Next step: plan", result.stdout)
        self.assertIn("Resume deferred: yes", result.stdout)
        self.assertIn("Note: rethink the approach", result.stdout)
        self.assertIn("Persisted step: plan", result.stdout)

        refreshed = store.get_task(task.id)
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.status, "in_progress")
        self.assertEqual(refreshed.workflow_current_step, "plan")
        self.assertEqual(refreshed.workflow_carried_output, "rethink the approach")

if __name__ == "__main__":
    unittest.main()
