"""Tests for the Foreman dashboard service, FastAPI transport, and React shell."""

from __future__ import annotations

import asyncio
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
import tempfile

import httpx

from foreman.dashboard_service import (
    DashboardService,
    DashboardValidationError,
)
from foreman.dashboard_backend import create_dashboard_app
from foreman.models import Event, Project, Run, Sprint, Task
from foreman.store import ForemanStore


class DashboardBackendTests(unittest.TestCase):
    """Test the extracted dashboard service, FastAPI backend, and React shell."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"
        cls.store = ForemanStore(cls.db_path)
        cls.store.initialize()

        # Seed test data
        cls.project = Project(
            id="proj-1",
            name="Test Project",
            repo_path="/tmp/test-project",
            workflow_id="development",
            created_at="2026-03-30T10:00:00Z",
            updated_at="2026-03-30T10:00:00Z",
        )
        cls.store.save_project(cls.project)

        cls.active_sprint = Sprint(
            id="sprint-1",
            project_id=cls.project.id,
            title="Active Sprint",
            goal="Ship the dashboard",
            status="active",
            order_index=1,
            created_at="2026-03-30T10:05:00Z",
            started_at="2026-03-30T10:10:00Z",
        )
        cls.store.save_sprint(cls.active_sprint)

        cls.done_sprint = Sprint(
            id="sprint-0",
            project_id=cls.project.id,
            title="Completed Sprint",
            goal="Previous work",
            status="completed",
            order_index=0,
            created_at="2026-03-20T10:00:00Z",
            started_at="2026-03-20T10:00:00Z",
            completed_at="2026-03-21T10:00:00Z",
        )
        cls.store.save_sprint(cls.done_sprint)

        cls.todo_task = Task(
            id="task-1",
            sprint_id=cls.active_sprint.id,
            project_id=cls.project.id,
            title="Todo task",
            status="todo",
            task_type="feature",
            order_index=1,
            created_at="2026-03-30T11:00:00Z",
        )
        cls.store.save_task(cls.todo_task)

        cls.in_progress_task = Task(
            id="task-2",
            sprint_id=cls.active_sprint.id,
            project_id=cls.project.id,
            title="In progress task",
            status="in_progress",
            task_type="feature",
            order_index=2,
            branch_name="feat/dashboard",
            assigned_role="developer",
            created_at="2026-03-30T11:05:00Z",
            started_at="2026-03-30T11:05:00Z",
        )
        cls.store.save_task(cls.in_progress_task)

        cls.blocked_task = Task(
            id="task-3",
            sprint_id=cls.active_sprint.id,
            project_id=cls.project.id,
            title="Blocked task",
            status="blocked",
            task_type="bug",
            order_index=3,
            blocked_reason="Awaiting approval",
            created_at="2026-03-30T11:10:00Z",
            started_at="2026-03-30T11:10:00Z",
        )
        cls.store.save_task(cls.blocked_task)

        cls.done_task = Task(
            id="task-4",
            sprint_id=cls.done_sprint.id,
            project_id=cls.project.id,
            title="Done task",
            status="done",
            task_type="feature",
            order_index=1,
            branch_name="feat/old-feature",
            created_at="2026-03-20T11:00:00Z",
            started_at="2026-03-20T11:00:00Z",
            completed_at="2026-03-20T12:00:00Z",
        )
        cls.store.save_task(cls.done_task)

        # Add a run with events
        cls.run_1 = Run(
            id="run-1",
            task_id=cls.in_progress_task.id,
            project_id=cls.project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude",
            status="completed",
            cost_usd=0.42,
            token_count=15000,
            created_at="2026-03-30T12:00:00Z",
            started_at="2026-03-30T12:00:00Z",
            completed_at="2026-03-30T12:30:00Z",
        )
        cls.store.save_run(cls.run_1)

        cls.event_1 = Event(
            id="event-1",
            run_id=cls.run_1.id,
            task_id=cls.in_progress_task.id,
            project_id=cls.project.id,
            event_type="agent.message",
            timestamp="2026-03-30T12:15:00Z",
            role_id="developer",
            payload={"text": "Working on the dashboard"},
        )
        cls.store.save_event(cls.event_1)

        cls.event_2 = Event(
            id="event-2",
            run_id=cls.run_1.id,
            task_id=cls.in_progress_task.id,
            project_id=cls.project.id,
            event_type="agent.file_change",
            timestamp="2026-03-30T12:20:00Z",
            role_id="developer",
            payload={"path": "foreman/dashboard_runtime.py"},
        )
        cls.store.save_event(cls.event_2)
        cls.api = DashboardService(
            cls.store,
            now_factory=lambda: datetime(
                2026,
                3,
                30,
                14,
                0,
                0,
                123456,
                tzinfo=timezone.utc,
            ),
        )
        cls.app = create_dashboard_app(str(cls.db_path))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls.temp_dir.cleanup()

    def request(self, method: str, url: str, **kwargs):
        """Send one request to the ASGI app without a live network server."""

        async def send():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(send())

    def call_route(self, route_path: str, **kwargs):
        """Call one FastAPI endpoint directly for routes that do not need a Request object."""

        route = next(
            route for route in self.app.routes if getattr(route, "path", None) == route_path
        )
        return asyncio.run(route.endpoint(**kwargs))

    def test_project_status_detection(self):
        """Project status is derived from task states."""
        self.assertEqual(self.api.get_project_status("proj-1"), "running")

        # Create another project with only blocked tasks
        project2 = Project(
            id="proj-2",
            name="Blocked Project",
            repo_path="/tmp/blocked",
            workflow_id="development",
        )
        self.store.save_project(project2)
        sprint2 = Sprint(
            id="sprint-2",
            project_id="proj-2",
            title="Blocked Sprint",
            status="active",
        )
        self.store.save_sprint(sprint2)
        task2 = Task(
            id="task-blocked-1",
            sprint_id="sprint-2",
            project_id="proj-2",
            title="Blocked",
            status="blocked",
        )
        self.store.save_task(task2)
        self.assertEqual(self.api.get_project_status("proj-2"), "blocked")

        # Project with no tasks -> idle
        project3 = Project(
            id="proj-3",
            name="Idle Project",
            repo_path="/tmp/idle",
            workflow_id="development",
        )
        self.store.save_project(project3)
        self.assertEqual(self.api.get_project_status("proj-3"), "idle")

    def test_api_projects_list(self):
        """API returns list of projects with task counts and totals."""
        result = self.api.list_projects()
        proj = next(p for p in result["projects"] if p["id"] == "proj-1")
        self.assertEqual(proj["name"], "Test Project")
        self.assertEqual(proj["status"], "running")
        self.assertIsNotNone(proj["active_sprint"])
        self.assertIn("task_counts", proj)
        self.assertIn("totals", proj)

    def test_api_project_sprints(self):
        """API returns sprints for a project."""
        result = self.api.list_project_sprints("proj-1")
        self.assertEqual(len(result["sprints"]), 2)
        sprint_ids = [s["id"] for s in result["sprints"]]
        self.assertIn("sprint-1", sprint_ids)
        self.assertIn("sprint-0", sprint_ids)

    def test_api_sprint_tasks(self):
        """API returns tasks for a sprint."""
        result = self.api.list_sprint_tasks("sprint-1")
        task_ids = [t["id"] for t in result["tasks"]]
        self.assertIn("task-1", task_ids)
        self.assertIn("task-2", task_ids)
        self.assertIn("task-3", task_ids)

    def test_api_sprint_events(self):
        """API returns events for a sprint."""
        events = self.api.list_sprint_events("sprint-1", limit=10)["events"]
        self.assertGreaterEqual(len(events), 2)
        event_types = [e["event_type"] for e in events]
        self.assertIn("agent.message", event_types)
        self.assertIn("agent.file_change", event_types)

    def test_dashboard_api_serializes_incremental_sprint_events(self):
        """Dashboard service can serialize sprint event batches after a known event."""
        events = self.api.list_sprint_events(
            "sprint-1",
            limit=10,
            after_event_id="event-1",
        )["events"]
        self.assertEqual([event["id"] for event in events], ["event-2"])
        self.assertEqual(events[0]["task_id"], "task-2")

    def test_dashboard_api_wraps_stream_messages_for_sse(self):
        """Dashboard service exposes the SSE payload contract separately from HTTP transport."""
        messages = self.api.list_sprint_stream_messages(
            "sprint-1",
            limit=10,
            after_event_id="event-1",
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["event_id"], "event-2")
        self.assertEqual(messages[0]["payload"]["type"], "event")
        self.assertEqual(messages[0]["payload"]["event"]["id"], "event-2")

    def test_dashboard_frontend_build_exists(self):
        """The built React dashboard assets are present for FastAPI to serve."""
        from foreman.dashboard_runtime import DASHBOARD_ASSETS_DIR, DASHBOARD_INDEX_PATH

        self.assertTrue(DASHBOARD_INDEX_PATH.is_file())
        self.assertTrue(DASHBOARD_ASSETS_DIR.is_dir())

    def test_fastapi_dashboard_shell_route_returns_html(self):
        """FastAPI serves the built React dashboard index."""
        response = self.call_route("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("<div id=\"root\"></div>", response.body.decode("utf-8"))
        self.assertIn("<title>Foreman Dashboard</title>", response.body.decode("utf-8"))

    def test_fastapi_projects_endpoint_returns_json(self):
        """FastAPI serves the project list over HTTP."""
        response = self.request("GET", "/api/projects")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response.headers["content-type"])
        data = response.json()
        project = next(item for item in data["projects"] if item["id"] == "proj-1")
        self.assertEqual(project["name"], "Test Project")
        self.assertEqual(project["status"], "running")

    def test_fastapi_task_detail_endpoint_returns_json(self):
        """FastAPI serves task detail over HTTP."""
        response = self.request("GET", "/api/tasks/task-2")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "In progress task")
        self.assertEqual(data["assigned_role"], "developer")
        self.assertEqual(len(data["runs"]), 1)

    def test_api_task_detail(self):
        """API returns task details with runs."""
        task = self.api.get_task("task-2")
        self.assertEqual(task["title"], "In progress task")
        self.assertEqual(task["status"], "in_progress")
        self.assertEqual(task["branch_name"], "feat/dashboard")
        self.assertEqual(task["assigned_role"], "developer")
        self.assertEqual(len(task["runs"]), 1)
        self.assertEqual(task["runs"][0]["role_id"], "developer")
        self.assertEqual(task["runs"][0]["token_count"], 15000)
        self.assertIn("total_token_count", task["totals"])

    def test_fastapi_dashboard_nested_route_returns_html(self):
        """Nested dashboard routes fall back to the React entrypoint."""
        response = self.call_route("/dashboard/{path:path}", path="projects/proj-1/sprints/sprint-1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("<div id=\"root\"></div>", response.body.decode("utf-8"))

    def test_fastapi_dev_mode_redirects_dashboard_shell_to_vite(self):
        """Frontend dev mode redirects dashboard shell routes to the Vite server."""
        app = create_dashboard_app(
            str(self.db_path),
            frontend_mode="dev",
            frontend_dev_url="http://127.0.0.1:5173",
        )
        route = next(route for route in app.routes if getattr(route, "path", None) == "/dashboard")

        response = asyncio.run(route.endpoint())
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "http://127.0.0.1:5173/dashboard")

    def test_human_message_event_storage(self):
        """Human guidance messages are persisted through the dashboard service contract."""
        result = self.api.create_human_message(
            self.in_progress_task.id,
            text="Please add more tests",
        )
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["task_id"], self.in_progress_task.id)
        events = self.store.list_events(task_id=self.in_progress_task.id)
        human_events = [e for e in events if e.event_type == "human.message"]
        self.assertEqual(len(human_events), 1)
        self.assertEqual(human_events[0].payload["text"], "Please add more tests")
        self.assertEqual(
            human_events[0].id,
            "evt-20260330140000123456-task-2",
        )

    def test_fastapi_dashboard_assets_route_returns_built_bundle(self):
        """FastAPI serves the built JavaScript bundle referenced by the React shell."""
        dashboard_html = self.call_route("/dashboard").body.decode("utf-8")
        match = re.search(r'src="(?P<path>/assets/[^"]+\.js)"', dashboard_html)
        self.assertIsNotNone(match)

        asset_response = self.call_route("/assets/{asset_path:path}", asset_path=match.group("path").replace("/assets/", "", 1))
        self.assertEqual(asset_response.status_code, 200)
        self.assertIn("javascript", asset_response.headers["content-type"])
        self.assertIn("createRoot", asset_response.body.decode("utf-8"))


class DashboardApproveDenyIntegrationTests(unittest.TestCase):
    """Integration tests for dashboard FastAPI endpoints and orchestrator wiring."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def request(self, method: str, url: str, **kwargs):
        """Send one request to a fresh app bound to the test database."""

        async def send():
            transport = httpx.ASGITransport(app=create_dashboard_app(str(self.db_path)))
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(send())

    def test_approve_action_calls_resume_human_gate(self):
        """Approve endpoint resumes the human gate through FastAPI."""
        store = ForemanStore(self.db_path)
        store.initialize()

        # Use development_with_architect workflow which has human_approval step
        project = Project(
            id="proj-approve-test",
            name="Test Project",
            repo_path="/tmp/test-project",
            workflow_id="development_with_architect",
        )
        store.save_project(project)

        sprint = Sprint(
            id="sprint-approve-test",
            project_id=project.id,
            title="Test Sprint",
            status="active",
        )
        store.save_sprint(sprint)

        task = Task(
            id="task-approve-test",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Blocked task for approval",
            status="blocked",
            task_type="feature",
            blocked_reason="Awaiting human approval",
            workflow_current_step="human_approval",
        )
        store.save_task(task)

        # Verify initial state
        self.assertEqual(task.status, "blocked")
        self.assertEqual(task.workflow_current_step, "human_approval")

        store.close()

        response = self.request("POST", f"/api/tasks/{task.id}/approve")
        updated_store = ForemanStore(self.db_path)
        updated_store.initialize()
        updated_task = updated_store.get_task(task.id)

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIsNotNone(updated_task)
        self.assertEqual(updated_task.status, "in_progress")
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["next_step"], "develop")
        self.assertTrue(result["deferred"])  # No native runner available

        updated_store.close()

    def test_deny_action_calls_resume_human_gate(self):
        """Deny endpoint resumes the human gate through FastAPI."""
        store = ForemanStore(self.db_path)
        store.initialize()

        # Use development_with_architect workflow which has human_approval step
        project = Project(
            id="proj-deny-test",
            name="Test Project",
            repo_path="/tmp/test-project",
            workflow_id="development_with_architect",
        )
        store.save_project(project)

        sprint = Sprint(
            id="sprint-deny-test",
            project_id=project.id,
            title="Test Sprint",
            status="active",
        )
        store.save_sprint(sprint)

        task = Task(
            id="task-deny-test",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Blocked task for denial",
            status="blocked",
            task_type="feature",
            blocked_reason="Awaiting human approval",
            workflow_current_step="human_approval",
        )
        store.save_task(task)

        # Verify initial state
        self.assertEqual(task.status, "blocked")
        self.assertEqual(task.workflow_current_step, "human_approval")

        store.close()

        response = self.request(
            "POST",
            f"/api/tasks/{task.id}/deny",
            json={"note": "Needs more work"},
        )
        updated_store = ForemanStore(self.db_path)
        updated_store.initialize()
        updated_task = updated_store.get_task(task.id)

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIsNotNone(updated_task)
        self.assertEqual(updated_task.status, "in_progress")
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["next_step"], "plan")  # Deny goes back to plan
        self.assertTrue(result["deferred"])  # No native runner available

        updated_store.close()

    def test_message_endpoint_persists_human_message(self):
        """Human message endpoint stores one event through FastAPI."""
        store = ForemanStore(self.db_path)
        store.initialize()

        project = Project(
            id="proj-message-test",
            name="Test Project",
            repo_path="/tmp/test-project",
            workflow_id="development",
        )
        store.save_project(project)

        sprint = Sprint(
            id="sprint-message-test",
            project_id=project.id,
            title="Test Sprint",
            status="active",
        )
        store.save_sprint(sprint)

        task = Task(
            id="task-message-test",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Task for human guidance",
            status="in_progress",
            task_type="feature",
        )
        store.save_task(task)

        run = Run(
            id="run-message-test",
            task_id=task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude",
            status="running",
        )
        store.save_run(run)
        store.close()

        response = self.request(
            "POST",
            f"/api/tasks/{task.id}/messages",
            json={"text": "Please handle the edge case."},
        )

        updated_store = ForemanStore(self.db_path)
        updated_store.initialize()
        events = updated_store.list_events(task_id=task.id)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "sent")
        self.assertEqual(payload["task_id"], task.id)
        self.assertTrue(any(event.event_type == "human.message" for event in events))
        self.assertTrue(
            any(
                event.event_type == "human.message"
                and event.payload.get("text") == "Please handle the edge case."
                for event in events
            )
        )

        updated_store.close()


class DashboardSettingsTests(unittest.TestCase):
    """Integration tests for dashboard settings, sprint creation, and task creation."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def _seed_project(self, project_id=None):
        """Seed a project with an active sprint and return (project, sprint)."""
        store = ForemanStore(self.db_path)
        store.initialize()
        pid = project_id or f"proj-settings-{id(self)}"
        project = Project(
            id=pid,
            name="Settings Test Project",
            repo_path="/tmp/settings-test",
            workflow_id="development",
        )
        store.save_project(project)
        sprint = Sprint(
            id=f"sprint-settings-{id(self)}",
            project_id=project.id,
            title="Active Sprint",
            status="active",
        )
        store.save_sprint(sprint)
        store.close()
        return project, sprint

    def _request(self, method, url, **kwargs):
        async def send():
            app = create_dashboard_app(str(self.db_path))
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, url, **kwargs)
        return asyncio.run(send())

    def test_get_project_settings_returns_current_state(self):
        project, _ = self._seed_project()
        response = self._request("GET", f"/api/projects/{project.id}/settings")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["project_id"], project.id)
        self.assertEqual(data["workflow_id"], "development")
        self.assertEqual(data["default_branch"], "main")
        self.assertIn("settings", data)
        self.assertIsInstance(data["settings"], dict)

    def test_patch_project_settings_updates_nested_settings(self):
        project, _ = self._seed_project()
        response = self._request(
            "PATCH",
            f"/api/projects/{project.id}/settings",
            json={"settings": {"max_step_visits": 10, "custom_key": "value"}},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["settings"]["max_step_visits"], 10)
        self.assertEqual(data["settings"]["custom_key"], "value")

    def test_patch_project_settings_rejects_unknown_top_level(self):
        project, _ = self._seed_project()
        response = self._request(
            "PATCH",
            f"/api/projects/{project.id}/settings",
            json={"unknown_field": "value"},
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_project_settings_updates_workflow_id(self):
        project, _ = self._seed_project()
        response = self._request(
            "PATCH",
            f"/api/projects/{project.id}/settings",
            json={"workflow_id": "development_secure"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["workflow_id"], "development_secure")

    def test_settings_endpoint_returns_404_for_unknown_project(self):
        self._seed_project()
        response = self._request("GET", "/api/projects/nonexistent/settings")
        self.assertEqual(response.status_code, 404)

    def test_create_sprint_endpoint_creates_planned_sprint(self):
        project, _ = self._seed_project()
        response = self._request(
            "POST",
            f"/api/projects/{project.id}/sprints",
            json={"title": "New Sprint", "goal": "Ship features"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("sprint-", data["id"])
        self.assertEqual(data["title"], "New Sprint")
        self.assertEqual(data["goal"], "Ship features")
        self.assertEqual(data["status"], "planned")

    def test_create_sprint_rejects_empty_title(self):
        project, _ = self._seed_project()
        response = self._request(
            "POST",
            f"/api/projects/{project.id}/sprints",
            json={"title": "", "goal": "No title"},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_sprint_returns_404_for_unknown_project(self):
        self._seed_project()
        response = self._request(
            "POST",
            "/api/projects/nonexistent/sprints",
            json={"title": "Test"},
        )
        self.assertEqual(response.status_code, 404)

    def test_create_task_endpoint_creates_todo_task(self):
        project, sprint = self._seed_project()
        response = self._request(
            "POST",
            f"/api/sprints/{sprint.id}/tasks",
            json={"title": "New Feature", "task_type": "feature", "acceptance_criteria": "Must pass tests"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("task-", data["id"])
        self.assertEqual(data["title"], "New Feature")
        self.assertEqual(data["task_type"], "feature")
        self.assertEqual(data["acceptance_criteria"], "Must pass tests")
        self.assertEqual(data["status"], "todo")

    def test_create_task_rejects_empty_title(self):
        _, sprint = self._seed_project()
        response = self._request(
            "POST",
            f"/api/sprints/{sprint.id}/tasks",
            json={"title": ""},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_task_rejects_invalid_type(self):
        _, sprint = self._seed_project()
        response = self._request(
            "POST",
            f"/api/sprints/{sprint.id}/tasks",
            json={"title": "Bad type", "task_type": "invalid"},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_task_returns_404_for_unknown_sprint(self):
        self._seed_project()
        response = self._request(
            "POST",
            "/api/sprints/nonexistent/tasks",
            json={"title": "Test"},
        )
        self.assertEqual(response.status_code, 404)

    def test_service_create_sprint_generates_stable_id(self):
        project, _ = self._seed_project()
        store = ForemanStore(self.db_path)
        store.initialize()
        api = DashboardService(store)
        result = api.create_sprint(project.id, title="My Sprint", goal="Do things")
        self.assertTrue(result["id"].startswith("sprint-"))
        self.assertIn("my-sprint", result["id"])
        self.assertEqual(result["status"], "planned")
        store.close()

    def test_service_create_task_generates_stable_id(self):
        _, sprint = self._seed_project()
        store = ForemanStore(self.db_path)
        store.initialize()
        api = DashboardService(store)
        result = api.create_task(sprint.id, title="Fix bug", task_type="fix", acceptance_criteria="No crash")
        self.assertTrue(result["id"].startswith("task-"))
        self.assertIn("fix-bug", result["id"])
        self.assertEqual(result["task_type"], "fix")
        store.close()

    def test_service_update_settings_rejects_non_dict_settings(self):
        project, _ = self._seed_project()
        store = ForemanStore(self.db_path)
        store.initialize()
        api = DashboardService(store)
        with self.assertRaises(DashboardValidationError):
            api.update_project_settings(project.id, updates={"settings": "not a dict"})
        store.close()


class DashboardSprintLifecycleTests(unittest.TestCase):
    """Tests for sprint status transitions, task field updates, and stop-agent endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def _request(self, method, url, **kwargs):
        async def send():
            app = create_dashboard_app(str(self.db_path))
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, url, **kwargs)
        return asyncio.run(send())

    _counter = 0

    def _next_id(self, prefix):
        DashboardSprintLifecycleTests._counter += 1
        return f"{prefix}-{DashboardSprintLifecycleTests._counter}"

    def _seed_planned_project(self):
        """Seed a project with only a planned sprint (no active sprint)."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-lc-p"),
            name="Lifecycle Project (planned)",
            repo_path="/tmp/lc-p",
            workflow_id="development",
        )
        store.save_project(project)
        planned = Sprint(
            id=self._next_id("sprint-lc-planned"),
            project_id=project.id,
            title="Planned Sprint",
            status="planned",
            order_index=0,
        )
        store.save_sprint(planned)
        store.close()
        return project, planned

    def _seed_active_project(self):
        """Seed a project with one active sprint containing one in-progress task."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-lc-a"),
            name="Lifecycle Project (active)",
            repo_path="/tmp/lc-a",
            workflow_id="development",
        )
        store.save_project(project)
        active = Sprint(
            id=self._next_id("sprint-lc-active"),
            project_id=project.id,
            title="Active Sprint",
            status="active",
            order_index=0,
            started_at="2026-03-31T09:00:00Z",
        )
        store.save_sprint(active)
        task = Task(
            id=self._next_id("task-lc-ip"),
            sprint_id=active.id,
            project_id=project.id,
            title="Running task",
            status="in_progress",
            task_type="feature",
        )
        store.save_task(task)
        run = Run(
            id=self._next_id("run-lc"),
            task_id=task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude",
            status="running",
        )
        store.save_run(run)
        store.close()
        return project, active, task

    def test_transition_planned_to_active(self):
        """PATCH /api/sprints/{id} transitions planned → active and sets started_at."""
        _, planned = self._seed_planned_project()
        response = self._request("PATCH", f"/api/sprints/{planned.id}", json={"status": "active"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "active")
        self.assertIsNotNone(data["started_at"])
        self.assertIsNone(data["completed_at"])

    def test_transition_active_to_completed(self):
        """PATCH /api/sprints/{id} transitions active → completed and sets completed_at."""
        _, active, _ = self._seed_active_project()
        response = self._request("PATCH", f"/api/sprints/{active.id}", json={"status": "completed"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "completed")
        self.assertIsNotNone(data["completed_at"])

    def test_transition_rejects_invalid_path(self):
        """PATCH /api/sprints/{id} rejects an invalid status transition."""
        _, active, _ = self._seed_active_project()
        response = self._request("PATCH", f"/api/sprints/{active.id}", json={"status": "planned"})
        self.assertEqual(response.status_code, 400)

    def test_transition_rejects_missing_status(self):
        """PATCH /api/sprints/{id} returns 400 when status field is absent."""
        _, planned = self._seed_planned_project()
        response = self._request("PATCH", f"/api/sprints/{planned.id}", json={})
        self.assertEqual(response.status_code, 400)

    def test_transition_returns_404_for_unknown_sprint(self):
        """PATCH /api/sprints/{id} returns 404 for nonexistent sprint."""
        response = self._request("PATCH", "/api/sprints/nonexistent", json={"status": "active"})
        self.assertEqual(response.status_code, 404)

    def test_update_task_description_and_priority(self):
        """PATCH /api/tasks/{id} updates description and priority fields."""
        _, _, task = self._seed_active_project()
        response = self._request(
            "PATCH",
            f"/api/tasks/{task.id}",
            json={"description": "Detailed description.", "priority": 2},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["description"], "Detailed description.")
        self.assertEqual(data["priority"], 2)

    def test_update_task_rejects_unknown_field(self):
        """PATCH /api/tasks/{id} returns 400 for fields not in the allowed set."""
        _, _, task = self._seed_active_project()
        response = self._request(
            "PATCH",
            f"/api/tasks/{task.id}",
            json={"status": "done"},
        )
        self.assertEqual(response.status_code, 400)

    def test_stop_agent_blocks_in_progress_tasks(self):
        """POST /api/projects/{id}/agent/stop marks in-progress tasks as blocked."""
        project, _, task = self._seed_active_project()
        response = self._request("POST", f"/api/projects/{project.id}/agent/stop")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["stopped"], 1)
        self.assertEqual(data["project_id"], project.id)

        store = ForemanStore(self.db_path)
        store.initialize()
        updated = store.get_task(task.id)
        self.assertEqual(updated.status, "blocked")
        self.assertIn("Stop requested", updated.blocked_reason)
        events = store.list_events(task_id=task.id)
        self.assertTrue(any(e.event_type == "human.stop_requested" for e in events))
        store.close()

    def test_stop_agent_returns_zero_when_no_active_sprint(self):
        """POST /api/projects/{id}/agent/stop returns stopped=0 when no active sprint."""
        store = ForemanStore(self.db_path)
        store.initialize()
        idle_project = Project(
            id="proj-lc-idle",
            name="Idle Project",
            repo_path="/tmp/idle",
            workflow_id="development",
        )
        store.save_project(idle_project)
        store.close()

        response = self._request("POST", f"/api/projects/{idle_project.id}/agent/stop")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stopped"], 0)

    def test_run_serialization_includes_timing_fields(self):
        """GET /api/tasks/{id} returns started_at, completed_at, session_id, branch_name on runs."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id="proj-run-serial",
            name="Run Serial",
            repo_path="/tmp/rs",
            workflow_id="development",
        )
        store.save_project(project)
        sprint = Sprint(
            id="sprint-run-serial",
            project_id=project.id,
            title="Sprint",
            status="active",
        )
        store.save_sprint(sprint)
        task = Task(
            id="task-run-serial",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Serialization task",
            status="in_progress",
            task_type="feature",
        )
        store.save_task(task)
        run = Run(
            id="run-serial",
            task_id=task.id,
            project_id=project.id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude",
            status="completed",
            session_id="sess-abc123",
            branch_name="feat/run-serial",
            started_at="2026-03-31T10:00:00Z",
            completed_at="2026-03-31T10:30:00Z",
        )
        store.save_run(run)
        store.close()

        response = self._request("GET", f"/api/tasks/{task.id}")
        self.assertEqual(response.status_code, 200)
        runs = response.json()["runs"]
        self.assertEqual(len(runs), 1)
        r = runs[0]
        self.assertEqual(r["session_id"], "sess-abc123")
        self.assertEqual(r["branch_name"], "feat/run-serial")
        self.assertEqual(r["started_at"], "2026-03-31T10:00:00Z")
        self.assertEqual(r["completed_at"], "2026-03-31T10:30:00Z")
