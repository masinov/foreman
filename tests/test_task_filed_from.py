"""A task an agent filed names the task it came from (service, API, CLI)."""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import tempfile
import unittest

import httpx

from foreman.api.app import create_dashboard_app
from foreman.domain.models import Project, Run, Sprint, Task
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.engine.results import AgentEventRecord
from foreman.services import Services
from foreman.store import ForemanStore
from test_cli import REPO_ROOT, cli_argv, cli_env


class FiledFromTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = str(Path(self._temp.name) / "foreman.db")
        with ForemanStore(self.db_path) as store:
            store.initialize()
            project = Project(
                id="p1", name="Demo", repo_path=self._temp.name, workflow_id="development"
            )
            sprint = Sprint(id="s1", project_id="p1", title="Active", status="active")
            parent = Task(
                id="parent", sprint_id="s1", project_id="p1", title="Parent", status="in_progress"
            )
            self.person_task = Task(
                id="person", sprint_id="s1", project_id="p1", title="By a person", created_by="human"
            )
            run = Run(
                id="run-1",
                task_id="parent",
                project_id="p1",
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
            )
            store.save_project(project)
            store.save_sprint(sprint)
            parent = store.save_task(parent)
            store.save_task(self.person_task)
            store.save_run(run)
            self.parent_key = store.get_task("parent").task_key
            ForemanOrchestrator(store).signals.persist_agent_event(
                run,
                parent,
                project,
                "developer",
                AgentEventRecord(
                    event_type="signal.task_created",
                    payload={"title": "Follow-up", "task_type": "fix"},
                    timestamp="2026-11-24T10:00:00Z",
                ),
            )
            backlog = store.get_backlog("p1")
            self.filed_id = store.list_tasks(sprint_id=backlog.id)[0].id

    def request(self, path: str) -> httpx.Response:
        app = create_dashboard_app(self.db_path, auth_token=None)

        async def call():
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
                return await c.get(path)

        return asyncio.run(call())

    def show(self, task_id: str) -> str:
        result = subprocess.run(
            cli_argv("task", "show", task_id, "--db", self.db_path),
            cwd=REPO_ROOT,
            env=cli_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_service_names_the_task_key_and_run(self) -> None:
        with ForemanStore(self.db_path) as store:
            detail = Services(store).tasks.get_task(self.filed_id)
            person = Services(store).tasks.get_task("person")
        self.assertEqual(
            detail["filed_from"],
            {
                "task_id": "parent",
                "task_key": self.parent_key,
                "title": "Parent",
                "run_id": "run-1",
                "exists": True,
            },
        )
        self.assertIsNone(person["filed_from"])

    def test_service_says_when_the_task_is_gone(self) -> None:
        with ForemanStore(self.db_path) as store:
            store._connection.execute("PRAGMA foreign_keys = OFF")
            store._connection.execute("DELETE FROM tasks WHERE id = 'parent'")
            store._connection.commit()
            detail = Services(store).tasks.get_task(self.filed_id)
        self.assertFalse(detail["filed_from"]["exists"])
        self.assertIsNone(detail["filed_from"]["task_key"])
        self.assertEqual(detail["filed_from"]["task_id"], "parent")

    def test_api_serves_it_on_the_task_detail(self) -> None:
        body = self.request(f"/api/v1/tasks/{self.filed_id}").json()
        self.assertEqual(body["filed_from"]["task_key"], self.parent_key)
        self.assertEqual(body["filed_from"]["run_id"], "run-1")
        self.assertIsNone(self.request("/api/v1/tasks/person").json()["filed_from"])

    def test_cli_prints_the_line_only_for_agent_filed_tasks(self) -> None:
        self.assertIn(
            f"Filed by the developer while working on {self.parent_key}", self.show(self.filed_id)
        )
        self.assertNotIn("while working on", self.show("person"))


if __name__ == "__main__":
    unittest.main()
