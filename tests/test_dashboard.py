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
    DashboardActionError,
    DashboardNotFoundError,
    DashboardValidationError,
)
from foreman.dashboard_backend import create_dashboard_app
from foreman.models import DecisionGate, Event, Project, Run, Sprint, Task
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


class DashboardAutonomyLevelTests(unittest.TestCase):
    """Tests for autonomy_level on projects."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def _seed_project(self, autonomy_level="supervised"):
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=f"proj-al-{id(self)}-{autonomy_level}",
            name="Autonomy Test",
            repo_path="/tmp/autonomy-test",
            workflow_id="development",
            autonomy_level=autonomy_level,
        )
        store.save_project(project)
        store.close()
        return project

    def _request(self, method, url, **kwargs):
        async def send():
            app = create_dashboard_app(str(self.db_path))
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)
        return asyncio.run(send())

    def test_project_defaults_to_supervised(self):
        """New projects persist autonomy_level='supervised' and it is returned in get_project."""
        project = self._seed_project()
        response = self._request("GET", f"/api/projects/{project.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["autonomy_level"], "supervised")

    def test_settings_returns_autonomy_level(self):
        """GET /api/projects/{id}/settings includes autonomy_level."""
        project = self._seed_project("directed")
        response = self._request("GET", f"/api/projects/{project.id}/settings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["autonomy_level"], "directed")

    def test_patch_settings_updates_autonomy_level(self):
        """PATCH /api/projects/{id}/settings accepts and persists a valid autonomy_level."""
        project = self._seed_project("supervised")
        response = self._request(
            "PATCH",
            f"/api/projects/{project.id}/settings",
            json={"autonomy_level": "autonomous"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["autonomy_level"], "autonomous")

        # Verify persisted
        get = self._request("GET", f"/api/projects/{project.id}/settings")
        self.assertEqual(get.json()["autonomy_level"], "autonomous")

    def test_patch_settings_rejects_invalid_autonomy_level(self):
        """PATCH /api/projects/{id}/settings returns 400 for an unknown autonomy_level value."""
        project = self._seed_project()
        response = self._request(
            "PATCH",
            f"/api/projects/{project.id}/settings",
            json={"autonomy_level": "turbo"},
        )
        self.assertEqual(response.status_code, 400)

    def test_autonomy_level_roundtrips_all_valid_values(self):
        """All three valid autonomy_level values survive a save/load cycle."""
        for level in ("directed", "supervised", "autonomous"):
            project = self._seed_project(level)
            response = self._request("GET", f"/api/projects/{project.id}/settings")
            self.assertEqual(response.json()["autonomy_level"], level, msg=f"failed for {level}")

    def test_transition_to_active_blocked_when_sprint_already_active(self):
        """PATCH /api/sprints/{id} with status=active returns 400 when another sprint is already active."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=f"proj-oas-{id(self)}",
            name="One Active Sprint",
            repo_path="/tmp/oas",
            workflow_id="development",
        )
        store.save_project(project)
        active_sprint = Sprint(
            id=f"sprint-oas-active-{id(self)}",
            project_id=project.id,
            title="Already Active",
            status="active",
        )
        planned_sprint = Sprint(
            id=f"sprint-oas-planned-{id(self)}",
            project_id=project.id,
            title="Wants to be Active",
            status="planned",
        )
        store.save_sprint(active_sprint)
        store.save_sprint(planned_sprint)
        store.close()

        response = self._request(
            "PATCH",
            f"/api/sprints/{planned_sprint.id}",
            json={"status": "active"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already active", response.json()["error"].lower())

    def test_transition_to_active_allowed_when_no_active_sprint(self):
        """PATCH /api/sprints/{id} with status=active succeeds when no sprint is currently active."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=f"proj-noactive-{id(self)}",
            name="No Active Sprint",
            repo_path="/tmp/noactive",
            workflow_id="development",
        )
        store.save_project(project)
        planned_sprint = Sprint(
            id=f"sprint-noactive-{id(self)}",
            project_id=project.id,
            title="Promote Me",
            status="planned",
        )
        store.save_sprint(planned_sprint)
        store.close()

        response = self._request(
            "PATCH",
            f"/api/sprints/{planned_sprint.id}",
            json={"status": "active"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "active")


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


class DashboardSprintTaskBacklogTests(unittest.TestCase):
    """Tests for sprint-31 backlog items: cancel task, inline tasks, dependencies, load-more."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    _counter = 0

    def _next_id(self, prefix):
        DashboardSprintTaskBacklogTests._counter += 1
        return f"{prefix}-{DashboardSprintTaskBacklogTests._counter}"

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

    def _seed_active(self):
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-bl"),
            name="Backlog Project",
            repo_path="/tmp/bl",
            workflow_id="development",
        )
        store.save_project(project)
        sprint = Sprint(
            id=self._next_id("sprint-bl"),
            project_id=project.id,
            title="Backlog Sprint",
            status="active",
            started_at="2026-03-31T09:00:00Z",
        )
        store.save_sprint(sprint)
        task = Task(
            id=self._next_id("task-bl"),
            sprint_id=sprint.id,
            project_id=project.id,
            title="Backlog task",
            status="in_progress",
            task_type="feature",
        )
        store.save_task(task)
        store.close()
        return project, sprint, task

    # ── Cancel task ──────────────────────────────────────────────────────────

    def test_cancel_task_sets_cancelled_status(self):
        """POST /api/tasks/{id}/cancel marks task as cancelled."""
        _, _, task = self._seed_active()
        response = self._request("POST", f"/api/tasks/{task.id}/cancel")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")

        store = ForemanStore(self.db_path)
        store.initialize()
        updated = store.get_task(task.id)
        self.assertEqual(updated.status, "cancelled")
        store.close()

    def test_cancel_task_rejects_done_task(self):
        """POST /api/tasks/{id}/cancel returns 400 when task is already done."""
        store = ForemanStore(self.db_path)
        store.initialize()
        _, sprint, _ = self._seed_active()
        done_task = Task(
            id=self._next_id("task-done"),
            sprint_id=sprint.id,
            project_id=sprint.project_id,
            title="Done task",
            status="done",
            task_type="feature",
        )
        store.save_task(done_task)
        store.close()
        response = self._request("POST", f"/api/tasks/{done_task.id}/cancel")
        self.assertEqual(response.status_code, 400)

    def test_cancel_task_returns_404_for_unknown_task(self):
        """POST /api/tasks/{id}/cancel returns 404 for nonexistent task."""
        response = self._request("POST", "/api/tasks/nonexistent/cancel")
        self.assertEqual(response.status_code, 404)

    # ── Sprint creation with initial tasks ───────────────────────────────────

    def test_create_sprint_with_initial_tasks(self):
        """POST /api/projects/{id}/sprints creates tasks when initial_tasks provided."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-init"),
            name="Init Tasks Project",
            repo_path="/tmp/it",
            workflow_id="development",
        )
        store.save_project(project)
        store.close()

        response = self._request(
            "POST",
            f"/api/projects/{project.id}/sprints",
            json={
                "title": "Sprint With Tasks",
                "goal": "Ship features",
                "initial_tasks": [
                    {"title": "First task", "task_type": "feature"},
                    {"title": "Second task", "task_type": "bug"},
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["tasks_created"], 2)

        store = ForemanStore(self.db_path)
        store.initialize()
        tasks = store.list_tasks(sprint_id=data["id"])
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].title, "First task")
        self.assertEqual(tasks[1].title, "Second task")
        store.close()

    def test_create_sprint_without_initial_tasks_still_works(self):
        """POST /api/projects/{id}/sprints without initial_tasks creates no tasks."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-noinit"),
            name="No Init Tasks Project",
            repo_path="/tmp/nit",
            workflow_id="development",
        )
        store.save_project(project)
        store.close()

        response = self._request(
            "POST",
            f"/api/projects/{project.id}/sprints",
            json={"title": "Bare Sprint"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["tasks_created"], 0)

    # ── Task dependencies in detail payload ──────────────────────────────────

    def test_get_task_includes_depends_on_task_ids(self):
        """GET /api/tasks/{id} returns depends_on_task_ids field."""
        store = ForemanStore(self.db_path)
        store.initialize()
        _, sprint, blocker = self._seed_active()
        dependent = Task(
            id=self._next_id("task-dep"),
            sprint_id=sprint.id,
            project_id=sprint.project_id,
            title="Dependent task",
            status="todo",
            task_type="feature",
            depends_on_task_ids=[blocker.id],
        )
        store.save_task(dependent)
        store.close()

        response = self._request("GET", f"/api/tasks/{dependent.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("depends_on_task_ids", data)
        self.assertEqual(data["depends_on_task_ids"], [blocker.id])

    # ── Event load-more (before_event_id) ────────────────────────────────────

    def test_list_sprint_events_before_cursor_returns_older_events(self):
        """GET /api/sprints/{id}/events?before=X returns events older than X."""
        store = ForemanStore(self.db_path)
        store.initialize()
        _, sprint, task = self._seed_active()
        run = Run(
            id=self._next_id("run-evts"),
            task_id=task.id,
            project_id=sprint.project_id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude",
            status="running",
        )
        store.save_run(run)
        # Create 4 events with distinct timestamps so pagination is deterministic.
        for i in range(4):
            event = Event(
                id=self._next_id("evt-pg"),
                run_id=run.id,
                task_id=task.id,
                project_id=sprint.project_id,
                event_type="agent.message",
                timestamp=f"2026-03-31T10:0{i}:00Z",
                payload={"seq": i},
            )
            store.save_event(event)
        all_events = store.list_recent_sprint_events(sprint.id, limit=50)
        store.close()
        self.assertEqual(len(all_events), 4)

        # Fetch only events before the 3rd event — should return events 0 and 1.
        cursor_id = all_events[2].id
        response = self._request(
            "GET",
            f"/api/sprints/{sprint.id}/events?before={cursor_id}&limit=10",
        )
        self.assertEqual(response.status_code, 200)
        returned = response.json()["events"]
        self.assertEqual(len(returned), 2)
        self.assertEqual(returned[0]["id"], all_events[0].id)
        self.assertEqual(returned[1]["id"], all_events[1].id)

    def test_list_sprint_events_has_more_flag_set_when_result_full(self):
        """GET /api/sprints/{id}/events returns has_more=True when limit is reached."""
        _, sprint, task = self._seed_active()
        store = ForemanStore(self.db_path)
        store.initialize()
        run = Run(
            id=self._next_id("run-hm"),
            task_id=task.id,
            project_id=sprint.project_id,
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude",
            status="running",
        )
        store.save_run(run)
        for i in range(3):
            event = Event(
                id=self._next_id("evt-hm"),
                run_id=run.id,
                task_id=task.id,
                project_id=sprint.project_id,
                event_type="agent.message",
                timestamp=f"2026-03-31T11:0{i}:00Z",
                payload={},
            )
            store.save_event(event)
        store.close()

        # Limit=2 with 3 events → has_more should be True.
        response = self._request(
            "GET",
            f"/api/sprints/{sprint.id}/events?limit=2",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["has_more"])


class DashboardTaskEditingTests(unittest.TestCase):
    """Tests for sprint-32: task title/type/criteria editing and sprint goal editing."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    _counter = 0

    def _next_id(self, prefix):
        DashboardTaskEditingTests._counter += 1
        return f"{prefix}-{DashboardTaskEditingTests._counter}"

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

    def _seed(self):
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-ed"),
            name="Edit Project",
            repo_path="/tmp/ed",
            workflow_id="development",
        )
        store.save_project(project)
        sprint = Sprint(
            id=self._next_id("sprint-ed"),
            project_id=project.id,
            title="Edit Sprint",
            status="active",
            goal="Original goal",
        )
        store.save_sprint(sprint)
        task = Task(
            id=self._next_id("task-ed"),
            sprint_id=sprint.id,
            project_id=project.id,
            title="Original title",
            status="todo",
            task_type="feature",
            acceptance_criteria="Original criteria",
        )
        store.save_task(task)
        store.close()
        return project, sprint, task

    # ── Task field editing ────────────────────────────────────────────────────

    def test_patch_task_title(self):
        """PATCH /api/tasks/{id} updates title."""
        _, _, task = self._seed()
        response = self._request(
            "PATCH",
            f"/api/tasks/{task.id}",
            json={"title": "Renamed title"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Renamed title")

    def test_patch_task_title_empty_rejected(self):
        """PATCH /api/tasks/{id} with empty title returns 400."""
        _, _, task = self._seed()
        response = self._request(
            "PATCH",
            f"/api/tasks/{task.id}",
            json={"title": "   "},
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_task_type(self):
        """PATCH /api/tasks/{id} updates task_type."""
        _, _, task = self._seed()
        response = self._request(
            "PATCH",
            f"/api/tasks/{task.id}",
            json={"task_type": "fix"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_type"], "fix")

    def test_patch_task_type_invalid_rejected(self):
        """PATCH /api/tasks/{id} with invalid task_type returns 400."""
        _, _, task = self._seed()
        response = self._request(
            "PATCH",
            f"/api/tasks/{task.id}",
            json={"task_type": "invalid_type"},
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_task_acceptance_criteria(self):
        """PATCH /api/tasks/{id} updates acceptance_criteria."""
        _, _, task = self._seed()
        response = self._request(
            "PATCH",
            f"/api/tasks/{task.id}",
            json={"acceptance_criteria": "New criteria text."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["acceptance_criteria"], "New criteria text.")

    def test_patch_task_acceptance_criteria_clear(self):
        """PATCH /api/tasks/{id} with null acceptance_criteria clears the field."""
        _, _, task = self._seed()
        response = self._request(
            "PATCH",
            f"/api/tasks/{task.id}",
            json={"acceptance_criteria": None},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["acceptance_criteria"])

    def test_patch_task_multiple_fields(self):
        """PATCH /api/tasks/{id} with title+type+criteria updates all three."""
        _, _, task = self._seed()
        response = self._request(
            "PATCH",
            f"/api/tasks/{task.id}",
            json={
                "title": "Multi-edit title",
                "task_type": "refactor",
                "acceptance_criteria": "Multi-edit criteria",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Multi-edit title")
        self.assertEqual(data["task_type"], "refactor")
        self.assertEqual(data["acceptance_criteria"], "Multi-edit criteria")

    # ── Sprint goal editing ───────────────────────────────────────────────────

    def test_patch_sprint_goal(self):
        """PATCH /api/sprints/{id} with goal updates the sprint goal."""
        _, sprint, _ = self._seed()
        response = self._request(
            "PATCH",
            f"/api/sprints/{sprint.id}",
            json={"goal": "New sprint goal"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["goal"], "New sprint goal")
        self.assertEqual(data["id"], sprint.id)

    def test_patch_sprint_goal_clear(self):
        """PATCH /api/sprints/{id} with empty goal clears it."""
        _, sprint, _ = self._seed()
        response = self._request(
            "PATCH",
            f"/api/sprints/{sprint.id}",
            json={"goal": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["goal"])

    def test_patch_sprint_status_still_works(self):
        """PATCH /api/sprints/{id} with status key still transitions the sprint."""
        _, sprint, _ = self._seed()
        response = self._request(
            "PATCH",
            f"/api/sprints/{sprint.id}",
            json={"status": "completed"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")

    def test_patch_sprint_unknown_field_rejected(self):
        """PATCH /api/sprints/{id} with unknown field (not status/title/goal) returns 400."""
        _, sprint, _ = self._seed()
        response = self._request(
            "PATCH",
            f"/api/sprints/{sprint.id}",
            json={"foo": "bar"},
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_sprint_order_index(self):
        """PATCH /api/sprints/{id} with order_index updates the sprint order."""
        _, sprint, _ = self._seed()
        response = self._request(
            "PATCH",
            f"/api/sprints/{sprint.id}",
            json={"order_index": 42},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], sprint.id)

        store = ForemanStore(self.db_path)
        store.initialize()
        updated = store.get_sprint(sprint.id)
        store.close()
        self.assertEqual(updated.order_index, 42)

    def test_patch_sprint_order_index_swap(self):
        """Swapping order_index between two sprints changes their list position."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-swap"),
            name="Swap Project",
            repo_path="/tmp/swap",
            workflow_id="development",
        )
        store.save_project(project)
        s1 = Sprint(
            id=self._next_id("sprint-swap"),
            project_id=project.id,
            title="Sprint One",
            status="planned",
            order_index=0,
        )
        s2 = Sprint(
            id=self._next_id("sprint-swap"),
            project_id=project.id,
            title="Sprint Two",
            status="planned",
            order_index=1,
        )
        store.save_sprint(s1)
        store.save_sprint(s2)
        store.close()

        self._request("PATCH", f"/api/sprints/{s1.id}", json={"order_index": 1})
        self._request("PATCH", f"/api/sprints/{s2.id}", json={"order_index": 0})

        response = self._request("GET", f"/api/projects/{project.id}/sprints")
        self.assertEqual(response.status_code, 200)
        sprints = response.json()["sprints"]
        self.assertEqual(sprints[0]["id"], s2.id)
        self.assertEqual(sprints[1]["id"], s1.id)

    def test_patch_sprint_order_index_swap_from_collision(self):
        """Reorder works when both sprints share the same order_index (e.g. default 0).

        The frontend fix assigns sequential indices rather than swapping values,
        so only the sprint that needs to move gets updated (the other keeps index 0).
        """
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-coll"),
            name="Collision Project",
            repo_path="/tmp/coll",
            workflow_id="development",
        )
        store.save_project(project)
        s1 = Sprint(
            id=self._next_id("sprint-coll"),
            project_id=project.id,
            title="First",
            status="planned",
            order_index=0,
        )
        s2 = Sprint(
            id=self._next_id("sprint-coll"),
            project_id=project.id,
            title="Second",
            status="planned",
            order_index=0,  # collides with s1
        )
        store.save_sprint(s1)
        store.save_sprint(s2)
        store.close()

        # Simulate the frontend sequential-index approach: s2 gets 0, s1 gets 1
        self._request("PATCH", f"/api/sprints/{s1.id}", json={"order_index": 1})

        response = self._request("GET", f"/api/projects/{project.id}/sprints")
        self.assertEqual(response.status_code, 200)
        sprints = response.json()["sprints"]
        self.assertEqual(sprints[0]["id"], s2.id)
        self.assertEqual(sprints[1]["id"], s1.id)

    def test_list_project_sprints_includes_order_index(self):
        """GET /api/projects/{id}/sprints response includes order_index for each sprint."""
        _, sprint, _ = self._seed()
        response = self._request("GET", f"/api/projects/{sprint.project_id}/sprints")
        self.assertEqual(response.status_code, 200)
        sprints = response.json()["sprints"]
        self.assertTrue(len(sprints) > 0)
        for s in sprints:
            self.assertIn("order_index", s)


class DashboardTier2Tests(unittest.TestCase):
    """Tests for sprint-33 Tier 2: project creation, start_agent, workflow_current_step."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    _counter = 0

    def _next_id(self, prefix):
        DashboardTier2Tests._counter += 1
        return f"{prefix}-{DashboardTier2Tests._counter}"

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

    # ── Project creation ──────────────────────────────────────────────────────

    def test_create_project_returns_200(self):
        """POST /api/projects creates a project and returns it."""
        response = self._request(
            "POST",
            "/api/projects",
            json={"name": "New Dashboard Project", "repo_path": "/tmp/ndp"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "New Dashboard Project")
        self.assertEqual(data["repo_path"], "/tmp/ndp")
        self.assertEqual(data["workflow_id"], "development")
        self.assertIn("id", data)

    def test_create_project_custom_workflow(self):
        """POST /api/projects accepts workflow_id."""
        response = self._request(
            "POST",
            "/api/projects",
            json={
                "name": "Secure Project",
                "repo_path": "/tmp/sec",
                "workflow_id": "development_secure",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["workflow_id"], "development_secure")

    def test_create_project_empty_name_rejected(self):
        """POST /api/projects with empty name returns 400."""
        response = self._request(
            "POST",
            "/api/projects",
            json={"name": "  ", "repo_path": "/tmp/x"},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_project_empty_repo_path_rejected(self):
        """POST /api/projects with empty repo_path returns 400."""
        response = self._request(
            "POST",
            "/api/projects",
            json={"name": "Valid Name", "repo_path": ""},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_project_appears_in_list(self):
        """Project created via POST /api/projects appears in GET /api/projects."""
        response = self._request(
            "POST",
            "/api/projects",
            json={"name": "Listed Project", "repo_path": "/tmp/lp"},
        )
        project_id = response.json()["id"]
        list_response = self._request("GET", "/api/projects")
        ids = [p["id"] for p in list_response.json()["projects"]]
        self.assertIn(project_id, ids)

    # ── Workflow step visibility ───────────────────────────────────────────────

    def test_list_sprint_tasks_includes_workflow_current_step(self):
        """GET /api/sprints/{id}/tasks includes workflow_current_step on each task."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-wcs"),
            name="WCS Project",
            repo_path="/tmp/wcs",
            workflow_id="development",
        )
        store.save_project(project)
        sprint = Sprint(
            id=self._next_id("sprint-wcs"),
            project_id=project.id,
            title="WCS Sprint",
            status="active",
        )
        store.save_sprint(sprint)
        task = Task(
            id=self._next_id("task-wcs"),
            sprint_id=sprint.id,
            project_id=project.id,
            title="Step task",
            status="in_progress",
            task_type="feature",
            workflow_current_step="develop",
        )
        store.save_task(task)
        store.close()

        response = self._request("GET", f"/api/sprints/{sprint.id}/tasks")
        self.assertEqual(response.status_code, 200)
        tasks = response.json()["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["workflow_current_step"], "develop")

    def test_get_task_includes_workflow_current_step(self):
        """GET /api/tasks/{id} includes workflow_current_step."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-gtwcs"),
            name="GT WCS",
            repo_path="/tmp/gtwcs",
            workflow_id="development",
        )
        store.save_project(project)
        sprint = Sprint(
            id=self._next_id("sprint-gtwcs"),
            project_id=project.id,
            title="Sprint",
            status="active",
        )
        store.save_sprint(sprint)
        task = Task(
            id=self._next_id("task-gtwcs"),
            sprint_id=sprint.id,
            project_id=project.id,
            title="Detail step task",
            status="in_progress",
            task_type="feature",
            workflow_current_step="review",
        )
        store.save_task(task)
        store.close()

        response = self._request("GET", f"/api/tasks/{task.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["workflow_current_step"], "review")

    # ── Start agent ────────────────────────────────────────────────────────────

    def test_start_agent_returns_404_for_unknown_project(self):
        """POST /api/projects/{id}/agent/start returns 404 for unknown project."""
        response = self._request(
            "POST",
            "/api/projects/does-not-exist/agent/start",
            json={},
        )
        self.assertEqual(response.status_code, 404)

    def test_start_agent_launched_for_known_project(self):
        """POST /api/projects/{id}/agent/start spawns a subprocess and returns started=true."""
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-sa"),
            name="Start Agent Project",
            repo_path="/tmp/sa",
            workflow_id="development",
        )
        store.save_project(project)
        store.close()

        import unittest.mock as mock
        with mock.patch("subprocess.Popen") as mock_popen:
            mock_proc = mock.MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            response = self._request(
                "POST",
                f"/api/projects/{project.id}/agent/start",
                json={},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["started"])
        self.assertEqual(data["project_id"], project.id)


class DashboardTaskEditEventTests(unittest.TestCase):
    """Tests for sprint-34: human.task_edited event emission on active/blocked task edits."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    _counter = 0

    def _next_id(self, prefix):
        DashboardTaskEditEventTests._counter += 1
        return f"{prefix}-{DashboardTaskEditEventTests._counter}"

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

    def _seed_task(self, status):
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-tee"),
            name="Edit Event Project",
            repo_path="/tmp/tee",
            workflow_id="development",
        )
        store.save_project(project)
        sprint = Sprint(
            id=self._next_id("sprint-tee"),
            project_id=project.id,
            title="Edit Event Sprint",
            status="active",
        )
        store.save_sprint(sprint)
        task = Task(
            id=self._next_id("task-tee"),
            sprint_id=sprint.id,
            project_id=project.id,
            title="Original title",
            status=status,
            task_type="feature",
            acceptance_criteria="Original criteria",
        )
        store.save_task(task)
        store.close()
        return project, sprint, task

    def _get_events(self, sprint_id):
        response = self._request("GET", f"/api/sprints/{sprint_id}/events")
        return response.json()["events"]

    # ── Event emitted for active/blocked tasks ────────────────────────────────

    def test_edit_inprogress_task_emits_event(self):
        """Editing an in_progress task emits a human.task_edited event."""
        _, sprint, task = self._seed_task("in_progress")
        self._request("PATCH", f"/api/tasks/{task.id}", json={"title": "Updated title"})
        events = self._get_events(sprint.id)
        edit_events = [e for e in events if e["event_type"] == "human.task_edited"]
        self.assertEqual(len(edit_events), 1)
        self.assertIn("title", edit_events[0]["payload"]["changed_fields"])

    def test_edit_blocked_task_emits_event(self):
        """Editing a blocked task emits a human.task_edited event."""
        _, sprint, task = self._seed_task("blocked")
        self._request("PATCH", f"/api/tasks/{task.id}", json={"acceptance_criteria": "New criteria"})
        events = self._get_events(sprint.id)
        edit_events = [e for e in events if e["event_type"] == "human.task_edited"]
        self.assertEqual(len(edit_events), 1)
        self.assertIn("acceptance_criteria", edit_events[0]["payload"]["changed_fields"])

    def test_edit_todo_task_does_not_emit_event(self):
        """Editing a todo task does not emit any event."""
        _, sprint, task = self._seed_task("todo")
        self._request("PATCH", f"/api/tasks/{task.id}", json={"title": "New title"})
        events = self._get_events(sprint.id)
        edit_events = [e for e in events if e["event_type"] == "human.task_edited"]
        self.assertEqual(len(edit_events), 0)

    def test_edit_done_task_does_not_emit_event(self):
        """Editing a done task does not emit any event."""
        _, sprint, task = self._seed_task("done")
        self._request("PATCH", f"/api/tasks/{task.id}", json={"title": "New title"})
        events = self._get_events(sprint.id)
        edit_events = [e for e in events if e["event_type"] == "human.task_edited"]
        self.assertEqual(len(edit_events), 0)

    def test_no_change_does_not_emit_event(self):
        """Patching a task with its existing values does not emit an event."""
        _, sprint, task = self._seed_task("in_progress")
        # Patch with the same title — no change
        self._request("PATCH", f"/api/tasks/{task.id}", json={"title": "Original title"})
        events = self._get_events(sprint.id)
        edit_events = [e for e in events if e["event_type"] == "human.task_edited"]
        self.assertEqual(len(edit_events), 0)

    def test_event_payload_lists_all_changed_fields(self):
        """human.task_edited payload enumerates every changed field."""
        _, sprint, task = self._seed_task("blocked")
        self._request(
            "PATCH",
            f"/api/tasks/{task.id}",
            json={"title": "Changed", "task_type": "fix", "priority": 3},
        )
        events = self._get_events(sprint.id)
        edit_events = [e for e in events if e["event_type"] == "human.task_edited"]
        self.assertEqual(len(edit_events), 1)
        changed = edit_events[0]["payload"]["changed_fields"]
        self.assertIn("title", changed)
        self.assertIn("task_type", changed)
        self.assertIn("priority", changed)


class DashboardRolesTests(unittest.TestCase):
    """Tests for GET /api/roles and PATCH /api/roles/{role_id} (sprint-36)."""

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

    # ── GET /api/roles ────────────────────────────────────────────────────────

    def test_list_roles_returns_200_with_roles_array(self):
        """GET /api/roles returns 200 with a non-empty roles list."""
        resp = self._request("GET", "/api/roles")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("roles", body)
        self.assertIsInstance(body["roles"], list)
        self.assertGreater(len(body["roles"]), 0)

    def test_list_roles_items_have_required_fields(self):
        """Each role item has the fields needed by the UI."""
        resp = self._request("GET", "/api/roles")
        self.assertEqual(resp.status_code, 200)
        roles = resp.json()["roles"]
        required = {"id", "name", "description", "backend", "model", "permission_mode",
                    "session_persistence", "timeout_minutes", "max_cost_usd", "source_path"}
        for role in roles:
            for field_name in required:
                self.assertIn(field_name, role, msg=f"Missing {field_name!r} in role {role.get('id')}")

    def test_list_roles_includes_developer_role(self):
        """The developer role shipped with the repo is present."""
        resp = self._request("GET", "/api/roles")
        ids = {r["id"] for r in resp.json()["roles"]}
        self.assertIn("developer", ids)

    # ── PATCH /api/roles/{role_id} ────────────────────────────────────────────

    def test_patch_unknown_role_returns_404(self):
        """PATCH on a non-existent role returns 404."""
        resp = self._request("PATCH", "/api/roles/no-such-role", json={"model": "x"})
        self.assertEqual(resp.status_code, 404)

    def test_patch_unknown_field_returns_400(self):
        """PATCH with an unknown field returns 400."""
        resp = self._request("PATCH", "/api/roles/developer", json={"prompt_template": "x"})
        self.assertEqual(resp.status_code, 400)

    def test_patch_invalid_timeout_type_returns_400(self):
        """PATCH with a float timeout_minutes returns 400."""
        resp = self._request("PATCH", "/api/roles/developer", json={"timeout_minutes": 1.5})
        self.assertEqual(resp.status_code, 400)

    def test_patch_negative_timeout_returns_400(self):
        """PATCH with a non-positive timeout_minutes returns 400."""
        resp = self._request("PATCH", "/api/roles/developer", json={"timeout_minutes": 0})
        self.assertEqual(resp.status_code, 400)

    def test_patch_invalid_cost_type_returns_400(self):
        """PATCH with a string max_cost_usd returns 400."""
        resp = self._request("PATCH", "/api/roles/developer", json={"max_cost_usd": "free"})
        self.assertEqual(resp.status_code, 400)

    def test_patch_empty_body_returns_role_unchanged(self):
        """PATCH with no fields returns 200 with the current role state."""
        resp = self._request("PATCH", "/api/roles/developer", json={})
        self.assertEqual(resp.status_code, 200)
        role = resp.json()
        self.assertEqual(role["id"], "developer")

    def test_patch_model_updates_and_persists(self):
        """PATCH model on a role writes to TOML and returns the updated value."""
        # Read current model value
        resp = self._request("GET", "/api/roles")
        developer = next(r for r in resp.json()["roles"] if r["id"] == "developer")
        original_model = developer["model"]

        new_model = "claude-test-model"
        resp = self._request("PATCH", "/api/roles/developer", json={"model": new_model})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["model"], new_model)

        # Re-read to confirm persistence
        resp2 = self._request("GET", "/api/roles")
        developer2 = next(r for r in resp2.json()["roles"] if r["id"] == "developer")
        self.assertEqual(developer2["model"], new_model)

        # Restore original value so we don't pollute other tests
        self._request("PATCH", "/api/roles/developer", json={"model": original_model})

    def test_patch_invalid_json_returns_400(self):
        """PATCH with malformed JSON returns 400."""
        async def send():
            app = create_dashboard_app(str(self.db_path))
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.patch(
                    "/api/roles/developer",
                    content=b"not-json",
                    headers={"content-type": "application/json"},
                )

        resp = asyncio.run(send())
        self.assertEqual(resp.status_code, 400)


class DashboardInterventionTests(unittest.TestCase):
    """Tests for sprint-36 intervention and ordering features."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"
        cls.store = ForemanStore(cls.db_path)
        cls.store.initialize()

        cls.project = Project(
            id="proj-intervention",
            name="Intervention Test",
            repo_path="/tmp/intervention",
            workflow_id="development",
            default_branch="main",
        )
        cls.store.save_project(cls.project)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls.temp_dir.cleanup()

    def _api(self):
        return DashboardService(self.store)

    def _create_sprint(self, sprint_id, status="planned", order_index=0):
        sprint = Sprint(
            id=sprint_id,
            project_id="proj-intervention",
            title=sprint_id,
            goal="test",
            status=status,
            order_index=order_index,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.save_sprint(sprint)
        return sprint

    def _create_task(self, task_id, sprint_id, status="todo"):
        task = Task(
            id=task_id,
            project_id="proj-intervention",
            sprint_id=sprint_id,
            title=task_id,
            task_type="feature",
            status=status,
            priority=0,
            order_index=0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.save_task(task)
        return task

    def test_stop_task_blocks_in_progress(self):
        sprint = self._create_sprint("spr-stop-1", status="active")
        self._create_task("task-stop-1", sprint.id, status="in_progress")

        result = self._api().stop_task("task-stop-1")
        self.assertEqual(result["status"], "blocked")

        updated = self.store.get_task("task-stop-1")
        self.assertEqual(updated.status, "blocked")
        self.assertIn("Stop requested", updated.blocked_reason)

    def test_stop_task_rejects_non_in_progress(self):
        self._create_task("task-stop-2", "spr-stop-1", status="todo")

        with self.assertRaises(DashboardValidationError):
            self._api().stop_task("task-stop-2")

    def test_stop_task_emits_event(self):
        # Reuse the sprint from test_stop_task_blocks_in_progress (spr-stop-1 is already active)
        self._create_task("task-stop-3", "spr-stop-1", status="in_progress")
        run = Run(
            id="run-stop-3",
            task_id="task-stop-3",
            project_id="proj-intervention",
            role_id="developer",
            workflow_step="develop",
            agent_backend="claude",
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.save_run(run)

        self._api().stop_task("task-stop-3")

        events = self.store.list_events(task_id="task-stop-3")
        stop_events = [e for e in events if e.event_type == "human.stop_requested"]
        self.assertEqual(len(stop_events), 1)
        self.assertEqual(stop_events[0].run_id, "run-stop-3")

    def test_stop_task_api_route(self):
        # Use a separate DB for the API route test to avoid connection sharing
        with tempfile.TemporaryDirectory() as td:
            api_db = Path(td) / "api.db"
            store = ForemanStore(api_db)
            store.initialize()
            store.save_project(Project(
                id="proj-api",
                name="API Test",
                repo_path="/tmp/api",
                workflow_id="development",
            ))
            store.save_sprint(Sprint(
                id="spr-stop-api",
                project_id="proj-api",
                title="stop-api",
                goal="test",
                status="active",
                order_index=0,
                created_at=datetime.now(timezone.utc).isoformat(),
            ))
            store.save_task(Task(
                id="task-stop-api",
                project_id="proj-api",
                sprint_id="spr-stop-api",
                title="stop-api-task",
                task_type="feature",
                status="in_progress",
                priority=0,
                order_index=0,
                created_at=datetime.now(timezone.utc).isoformat(),
            ))
            store.close()

            app = create_dashboard_app(str(api_db))
            transport = httpx.ASGITransport(app=app)

            async def send():
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    return await client.post("/api/tasks/task-stop-api/stop")

            resp = asyncio.run(send())
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["status"], "blocked")


class DashboardDeleteSprintTests(unittest.TestCase):
    """Tests for sprint deletion."""

    def _api(self):
        temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(temp_dir.name) / "foreman.db"
        store = ForemanStore(db_path)
        store.initialize()
        store.save_project(Project(
            id="proj-del",
            name="Deletion Test",
            repo_path="/tmp/del",
            workflow_id="development",
        ))
        return store, temp_dir, DashboardService(store)

    def test_delete_sprint_exists(self):
        store, temp_dir, api = self._api()
        sprint = Sprint(
            id="spr-del",
            project_id="proj-del",
            title="To Delete",
            status="planned",
            order_index=0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        store.save_sprint(sprint)

        result = api.delete_sprint("spr-del")
        self.assertEqual(result["ok"], "deleted")
        self.assertIsNone(store.get_sprint("spr-del"))

        store.close()
        temp_dir.cleanup()

    def test_delete_sprint_not_found(self):
        _, temp_dir, api = self._api()
        with self.assertRaises(DashboardNotFoundError):
            api.delete_sprint("nonexistent")
        temp_dir.cleanup()


class DashboardDecisionGateTests(unittest.TestCase):
    """Tests for decision gate create / list / resolve endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "foreman.db"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    _counter = 0

    def _next_id(self, prefix):
        DashboardDecisionGateTests._counter += 1
        return f"{prefix}-{DashboardDecisionGateTests._counter}"

    def _seed(self):
        store = ForemanStore(self.db_path)
        store.initialize()
        project = Project(
            id=self._next_id("proj-gate"),
            name="Gate Test Project",
            repo_path="/tmp/gate-test",
            workflow_id="development",
        )
        store.save_project(project)
        sprint_a = Sprint(id=self._next_id("spr-a"), project_id=project.id, title="Sprint A", status="planned", order_index=0)
        sprint_b = Sprint(id=self._next_id("spr-b"), project_id=project.id, title="Sprint B", status="planned", order_index=1)
        store.save_sprint(sprint_a)
        store.save_sprint(sprint_b)
        store.close()
        return project, sprint_a, sprint_b

    def _request(self, method, url, **kwargs):
        async def send():
            app = create_dashboard_app(str(self.db_path))
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)
        return asyncio.run(send())

    def test_create_gate_returns_pending_gate(self):
        """POST /api/projects/{id}/gates creates and returns a pending gate."""
        project, sprint_a, _ = self._seed()
        response = self._request(
            "POST",
            f"/api/projects/{project.id}/gates",
            json={
                "sprint_id": sprint_a.id,
                "conflict_description": "Sprint B depends on work not yet in Sprint A.",
                "suggested_order": [sprint_a.id],
                "suggested_reason": "A must complete before B.",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["project_id"], project.id)
        self.assertEqual(data["sprint_id"], sprint_a.id)
        self.assertIn("gate-", data["id"])
        self.assertEqual(data["conflict_description"], "Sprint B depends on work not yet in Sprint A.")

    def test_create_gate_rejects_empty_description(self):
        """POST /api/projects/{id}/gates returns 400 for empty conflict_description."""
        project, sprint_a, _ = self._seed()
        response = self._request(
            "POST",
            f"/api/projects/{project.id}/gates",
            json={"sprint_id": sprint_a.id, "conflict_description": "   "},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_gate_rejects_unknown_project(self):
        """POST /api/projects/{id}/gates returns 404 for unknown project."""
        response = self._request(
            "POST",
            "/api/projects/does-not-exist/gates",
            json={"sprint_id": "any", "conflict_description": "desc"},
        )
        self.assertEqual(response.status_code, 404)

    def test_list_gates_returns_pending_only_when_filtered(self):
        """GET /api/projects/{id}/gates?status=pending returns only pending gates."""
        project, sprint_a, _ = self._seed()
        # Create a gate
        self._request(
            "POST",
            f"/api/projects/{project.id}/gates",
            json={"sprint_id": sprint_a.id, "conflict_description": "conflict 1"},
        )
        response = self._request("GET", f"/api/projects/{project.id}/gates?status=pending")
        self.assertEqual(response.status_code, 200)
        gates = response.json()["gates"]
        self.assertTrue(len(gates) >= 1)
        self.assertTrue(all(g["status"] == "pending" for g in gates))

    def test_list_gates_without_filter_returns_all(self):
        """GET /api/projects/{id}/gates without filter returns all gates."""
        project, sprint_a, _ = self._seed()
        self._request(
            "POST",
            f"/api/projects/{project.id}/gates",
            json={"sprint_id": sprint_a.id, "conflict_description": "conflict list-all"},
        )
        response = self._request("GET", f"/api/projects/{project.id}/gates")
        self.assertEqual(response.status_code, 200)
        self.assertIn("gates", response.json())

    def test_resolve_gate_accepted_reorders_sprints(self):
        """PATCH /api/gates/{id} with accepted applies suggested_order to sprint order_index."""
        project, sprint_a, sprint_b = self._seed()
        create_resp = self._request(
            "POST",
            f"/api/projects/{project.id}/gates",
            json={
                "sprint_id": sprint_a.id,
                "conflict_description": "B must come before A",
                "suggested_order": [sprint_b.id, sprint_a.id],
            },
        )
        gate_id = create_resp.json()["id"]

        resolve_resp = self._request(
            "PATCH",
            f"/api/gates/{gate_id}",
            json={"resolution": "accepted"},
        )
        self.assertEqual(resolve_resp.status_code, 200)
        self.assertEqual(resolve_resp.json()["status"], "accepted")

        # Verify sprints were reordered
        store = ForemanStore(self.db_path)
        store.initialize()
        b = store.get_sprint(sprint_b.id)
        a = store.get_sprint(sprint_a.id)
        store.close()
        self.assertEqual(b.order_index, 0)
        self.assertEqual(a.order_index, 1)

    def test_resolve_gate_rejected_does_not_reorder(self):
        """PATCH /api/gates/{id} with rejected closes the gate without changing sprint order."""
        project, sprint_a, sprint_b = self._seed()
        create_resp = self._request(
            "POST",
            f"/api/projects/{project.id}/gates",
            json={
                "sprint_id": sprint_a.id,
                "conflict_description": "order conflict",
                "suggested_order": [sprint_b.id, sprint_a.id],
            },
        )
        gate_id = create_resp.json()["id"]

        store = ForemanStore(self.db_path)
        store.initialize()
        orig_a_order = store.get_sprint(sprint_a.id).order_index
        orig_b_order = store.get_sprint(sprint_b.id).order_index
        store.close()

        resolve_resp = self._request(
            "PATCH",
            f"/api/gates/{gate_id}",
            json={"resolution": "rejected"},
        )
        self.assertEqual(resolve_resp.status_code, 200)
        self.assertEqual(resolve_resp.json()["status"], "rejected")

        store = ForemanStore(self.db_path)
        store.initialize()
        self.assertEqual(store.get_sprint(sprint_a.id).order_index, orig_a_order)
        self.assertEqual(store.get_sprint(sprint_b.id).order_index, orig_b_order)
        store.close()

    def test_resolve_gate_cannot_resolve_already_resolved(self):
        """PATCH /api/gates/{id} returns 400 when gate is not pending."""
        project, sprint_a, _ = self._seed()
        create_resp = self._request(
            "POST",
            f"/api/projects/{project.id}/gates",
            json={"sprint_id": sprint_a.id, "conflict_description": "desc"},
        )
        gate_id = create_resp.json()["id"]
        self._request("PATCH", f"/api/gates/{gate_id}", json={"resolution": "dismissed"})
        second = self._request("PATCH", f"/api/gates/{gate_id}", json={"resolution": "dismissed"})
        self.assertEqual(second.status_code, 400)

    def test_resolve_gate_rejects_invalid_resolution(self):
        """PATCH /api/gates/{id} returns 400 for an unrecognised resolution value."""
        project, sprint_a, _ = self._seed()
        create_resp = self._request(
            "POST",
            f"/api/projects/{project.id}/gates",
            json={"sprint_id": sprint_a.id, "conflict_description": "desc"},
        )
        gate_id = create_resp.json()["id"]
        response = self._request("PATCH", f"/api/gates/{gate_id}", json={"resolution": "ignored"})
        self.assertEqual(response.status_code, 400)
