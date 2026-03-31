"""Tests for the Foreman dashboard backend and legacy shell."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from pathlib import Path
import tempfile

import httpx

from foreman.dashboard_api import DashboardAPI
from foreman.dashboard_backend import create_dashboard_app
from foreman.models import Event, Project, Run, Sprint, Task
from foreman.store import ForemanStore


class DashboardBackendTests(unittest.TestCase):
    """Test the extracted dashboard API, FastAPI backend, and legacy shell."""

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
            payload={"path": "foreman/dashboard.py"},
        )
        cls.store.save_event(cls.event_2)
        cls.api = DashboardAPI(
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
        """Dashboard API can serialize sprint event batches after a known event."""
        events = self.api.list_sprint_events(
            "sprint-1",
            limit=10,
            after_event_id="event-1",
        )["events"]
        self.assertEqual([event["id"] for event in events], ["event-2"])
        self.assertEqual(events[0]["task_id"], "task-2")

    def test_dashboard_api_wraps_stream_messages_for_sse(self):
        """Dashboard API exposes the SSE payload contract separately from HTTP transport."""
        messages = self.api.list_sprint_stream_messages(
            "sprint-1",
            limit=10,
            after_event_id="event-1",
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["event_id"], "event-2")
        self.assertEqual(messages[0]["payload"]["type"], "event")
        self.assertEqual(messages[0]["payload"]["event"]["id"], "event-2")

    def test_dashboard_html_content(self):
        """Dashboard HTML contains expected elements."""
        from foreman.dashboard import DASHBOARD_HTML
        self.assertIn("<title>Foreman Dashboard</title>", DASHBOARD_HTML)
        self.assertIn("Projects", DASHBOARD_HTML)
        self.assertIn("api/projects", DASHBOARD_HTML)

    def test_fastapi_dashboard_shell_route_returns_html(self):
        """FastAPI serves the current legacy dashboard shell."""
        response = self.request("GET", "/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Foreman Dashboard", response.text)

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

    def test_dashboard_detail_panel_html(self):
        """Dashboard HTML contains detail panel elements."""
        from foreman.dashboard import DASHBOARD_HTML
        self.assertIn("detail-panel", DASHBOARD_HTML)
        self.assertIn("detail-overlay", DASHBOARD_HTML)
        self.assertIn("showTaskDetail", DASHBOARD_HTML)
        self.assertIn("hideDetail", DASHBOARD_HTML)
        self.assertIn("Run History", DASHBOARD_HTML)
        self.assertIn("Acceptance Criteria", DASHBOARD_HTML)

    def test_dashboard_activity_input_html(self):
        """Dashboard HTML contains activity input elements."""
        from foreman.dashboard import DASHBOARD_HTML
        self.assertIn("activity-input", DASHBOARD_HTML)
        self.assertIn("humanInput", DASHBOARD_HTML)
        self.assertIn("sendHumanMessage", DASHBOARD_HTML)
        self.assertIn("autoResize", DASHBOARD_HTML)

    def test_human_message_event_storage(self):
        """Human guidance messages are persisted through the dashboard API contract."""
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

    def test_dashboard_activity_filter_html(self):
        """Dashboard HTML contains activity filter elements."""
        from foreman.dashboard import DASHBOARD_HTML
        self.assertIn("activity-filter", DASHBOARD_HTML)
        self.assertIn("activityFilterMenu", DASHBOARD_HTML)
        self.assertIn("filterEvents", DASHBOARD_HTML)
        self.assertIn("toggleFilterMenu", DASHBOARD_HTML)

    def test_dashboard_streaming_transport_html(self):
        """Dashboard HTML wires the activity feed to the sprint event stream."""
        from foreman.dashboard import DASHBOARD_HTML
        self.assertIn("EventSource", DASHBOARD_HTML)
        self.assertIn("/api/sprints/${sprintId}/stream", DASHBOARD_HTML)
        self.assertIn("openSprintStream", DASHBOARD_HTML)
        self.assertIn("queueSprintRefresh", DASHBOARD_HTML)

    def test_dashboard_project_switcher_html(self):
        """Dashboard HTML contains project switcher elements."""
        from foreman.dashboard import DASHBOARD_HTML
        self.assertIn("project-switcher", DASHBOARD_HTML)
        self.assertIn("projectSwitcherMenu", DASHBOARD_HTML)
        self.assertIn("switchProject", DASHBOARD_HTML)
        self.assertIn("toggleProjectSwitcher", DASHBOARD_HTML)


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
