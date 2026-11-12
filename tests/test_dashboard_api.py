"""The shape of the dashboard API: versioned paths, one error envelope."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import httpx

from foreman.dashboard.app import ROUTERS, _is_intake_path, create_dashboard_app
from foreman.dashboard.context import API_PREFIXES, ApiContext
from foreman.dashboard.streaming import event_stream_response
from foreman.dashboard_service import DashboardService
from foreman.models import Event, Project, Run, Sprint, Task
from foreman.store import ForemanStore


class DashboardApiShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = str(Path(self._temp.name) / "foreman.db")
        with ForemanStore(self.db_path) as store:
            store.initialize()
            store.save_project(
                Project(id="p1", name="Demo", repo_path=self._temp.name, workflow_id="development")
            )
            store.save_sprint(Sprint(id="s1", project_id="p1", title="First", status="active"))
            store.save_task(Task(id="t1", sprint_id="s1", project_id="p1", title="Do it"))
        self.app = create_dashboard_app(self.db_path, auth_token=None)

    def request(self, method: str, path: str, *, token: str | None = None, app=None, **kwargs):
        async def call():
            transport = httpx.ASGITransport(app=app or self.app, raise_app_exceptions=False)
            headers = dict(kwargs.pop("headers", {}))
            if token:
                headers["Authorization"] = f"Bearer {token}"
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.request(method, path, headers=headers, **kwargs)

        return asyncio.run(call())

    # ── versioned paths ──────────────────────────────────────────────────

    def test_every_route_answers_under_the_versioned_and_the_original_path(self) -> None:
        for path in ("/projects", "/projects/p1", "/sprints/s1/tasks", "/tasks/t1", "/roles"):
            with self.subTest(path=path):
                versioned = self.request("GET", f"/api/v1{path}")
                original = self.request("GET", f"/api{path}")
                self.assertEqual(versioned.status_code, 200)
                self.assertEqual(original.status_code, 200)
                self.assertEqual(versioned.json(), original.json())

    def test_every_router_is_mounted_under_every_prefix(self) -> None:
        context = ApiContext(db_path=self.db_path, manager_enabled=True)
        routes = [
            (method, route.path)
            for module in ROUTERS
            for route in module.build_router(context).routes
            for method in route.methods
        ]

        self.assertEqual(API_PREFIXES, ("/api/v1", "/api"))
        self.assertEqual(len(ROUTERS), 10)
        self.assertEqual(len(routes), len(set(routes)), "a route is defined twice")
        self.assertGreater(len(routes), 35)
        # No route carries a prefix of its own; the application adds it.
        self.assertFalse([path for _, path in routes if path.startswith("/api")])
        # Each router's first parameterless GET answers under both prefixes.
        for module in ROUTERS:
            for route in module.build_router(context).routes:
                if "GET" in route.methods and "{" not in route.path:
                    for prefix in API_PREFIXES:
                        with self.subTest(route=route.path, prefix=prefix):
                            self.assertEqual(
                                self.request("GET", prefix + route.path).status_code, 200
                            )

    def test_a_write_through_the_versioned_path_takes_effect(self) -> None:
        response = self.request("POST", "/api/v1/tasks/t1/cancel")

        self.assertEqual(response.status_code, 200)
        with ForemanStore(self.db_path) as store:
            self.assertEqual(store.get_task("t1").status, "cancelled")

    # ── one error envelope ───────────────────────────────────────────────

    def assert_envelope(self, response, status: int, code: str) -> str:
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(set(body), {"error", "code"})
        self.assertEqual(body["code"], code)
        self.assertIsInstance(body["error"], str)
        self.assertTrue(body["error"])
        return body["error"]

    def test_errors_are_a_sentence_and_a_code_whatever_went_wrong(self) -> None:
        self.assert_envelope(self.request("GET", "/api/v1/tasks/nope"), 404, "not_found")
        self.assert_envelope(self.request("GET", "/api/v1/no-such-route"), 404, "not_found")
        self.assert_envelope(self.request("PUT", "/api/v1/projects"), 405, "method_not_allowed")
        self.assert_envelope(
            self.request("PATCH", "/api/v1/sprints/s1", json={"status": "planned"}),
            400,
            "invalid_request",
        )
        message = self.assert_envelope(
            self.request("GET", "/api/v1/projects/p1/engine/commands?limit=many"),
            400,
            "invalid_request",
        )
        self.assertIn("limit", message)

    def test_a_bug_answers_with_the_envelope_and_no_internals(self) -> None:
        with mock.patch(
            "foreman.dashboard_service.DashboardService.list_projects",
            side_effect=KeyError("secret-internal-detail"),
        ):
            with self.assertLogs("foreman.dashboard", level="ERROR"):
                response = self.request("GET", "/api/v1/projects")

        message = self.assert_envelope(response, 500, "internal_error")
        self.assertNotIn("secret-internal-detail", message)

    def test_authentication_failures_use_the_envelope(self) -> None:
        app = create_dashboard_app(self.db_path, auth_token="dashboard-secret")

        self.assert_envelope(self.request("GET", "/api/v1/projects", app=app), 401, "unauthorized")
        ok = self.request("GET", "/api/v1/projects", app=app, token="dashboard-secret")
        self.assertEqual(ok.status_code, 200)

    # ── typed request bodies ─────────────────────────────────────────────

    def test_a_field_of_the_wrong_type_is_refused_by_name(self) -> None:
        cases = (
            ("/api/v1/sprints/s1/tasks", {"title": None}, "title"),
            ("/api/v1/sprints/s1/tasks", {"title": 42}, "title"),
            ("/api/v1/sprints/s1/tasks", {"title": "T", "depends_on": "t1"}, "depends_on"),
            ("/api/v1/projects/p1/sprints", {"title": "S", "initial_tasks": {"title": "x"}}, "initial_tasks"),
            ("/api/v1/tasks/t1/messages", {"text": ["a", "b"]}, "text"),
        )
        for path, body, field in cases:
            with self.subTest(path=path, body=body):
                message = self.assert_envelope(
                    self.request("POST", path, json=body), 400, "invalid_request"
                )
                self.assertIn(f"'{field}", message)
        with ForemanStore(self.db_path) as store:
            self.assertEqual([task.title for task in store.list_tasks(sprint_id="s1")], ["Do it"])

    def test_a_null_title_is_no_longer_stored_as_the_text_none(self) -> None:
        self.request("POST", "/api/v1/sprints/s1/tasks", json={"title": None})

        with ForemanStore(self.db_path) as store:
            self.assertNotIn("None", [task.title for task in store.list_tasks(sprint_id="s1")])

    def test_a_well_typed_body_is_accepted_and_unknown_fields_are_ignored(self) -> None:
        response = self.request(
            "POST",
            "/api/v1/sprints/s1/tasks",
            json={"title": "Typed", "task_type": "fix", "colour": "blue"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        with ForemanStore(self.db_path) as store:
            created = [task for task in store.list_tasks(sprint_id="s1") if task.title == "Typed"]
        self.assertEqual([task.task_type for task in created], ["fix"])

    def test_the_service_still_owns_the_rule_for_a_missing_title(self) -> None:
        message = self.assert_envelope(
            self.request("POST", "/api/v1/sprints/s1/tasks", json={}), 400, "invalid_request"
        )
        self.assertNotIn("'title'", message)  # the service's sentence, not a type error

    def test_a_body_that_is_not_declared_as_json_is_still_refused(self) -> None:
        response = self.request(
            "POST",
            "/api/v1/sprints/s1/tasks",
            content='{"title": "sneaky"}',
            headers={"Content-Type": "text/plain"},
        )

        message = self.assert_envelope(response, 400, "invalid_request")
        self.assertIn("application/json", message)

    # ── the intake path is recognised under every prefix, and only there ─

    def test_intake_path_detection(self) -> None:
        self.assertTrue(_is_intake_path("/api/v1/projects/p1/intake"))
        self.assertTrue(_is_intake_path("/api/projects/p1/intake"))
        # A project called "v1" under the original prefix is still a project.
        self.assertTrue(_is_intake_path("/api/projects/v1/intake"))
        for path in (
            "/api/v1/projects/p1/intake/extra",
            "/api/v1/projects/p1/sprints",
            "/api/v1/tasks/t1",
            "/api/v1/v1/projects/p1/intake",
            "/projects/p1/intake",
        ):
            with self.subTest(path=path):
                self.assertFalse(_is_intake_path(path))

    def test_a_project_api_token_reaches_intake_and_nothing_else_under_v1(self) -> None:
        with ForemanStore(self.db_path) as store:
            _, secret = store.create_api_token(project_id="p1", name="alerts", scopes=("intake",))
        app = create_dashboard_app(self.db_path, auth_token="dashboard-secret")

        filed = self.request(
            "POST",
            "/api/v1/projects/p1/intake",
            app=app,
            token=secret,
            json={"title": "Disk full", "description": "web-3 is at 98%."},
        )
        self.assertIn(filed.status_code, (200, 201), filed.text)

        refused = self.request("GET", "/api/v1/projects", app=app, token=secret)
        self.assert_envelope(refused, 403, "forbidden")


class ProjectEventStreamTests(unittest.TestCase):
    """One stream for a whole project, across its sprints."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = str(Path(self._temp.name) / "foreman.db")
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        for project_id in ("p1", "other"):
            self.store.save_project(
                Project(id=project_id, name=project_id, repo_path=self._temp.name,
                        workflow_id="development")
            )
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="One", status="completed"))
        self.store.save_sprint(Sprint(id="s2", project_id="p1", title="Two", status="active"))
        self.store.save_sprint(Sprint(id="sx", project_id="other", title="X", status="active"))
        self.add_event("e1", project="p1", sprint="s1", stamp="2026-01-01T00:00:01Z")
        self.add_event("e2", project="p1", sprint="s2", stamp="2026-01-01T00:00:02Z")
        self.add_event("ex", project="other", sprint="sx", stamp="2026-01-01T00:00:03Z")
        self.add_event("e3", project="p1", sprint="s2", stamp="2026-01-01T00:00:04Z")
        self.api = DashboardService(self.store)

    def add_event(self, event_id: str, *, project: str, sprint: str, stamp: str) -> None:
        task_id = f"task-{event_id}"
        self.store.save_task(Task(id=task_id, sprint_id=sprint, project_id=project, title="T"))
        self.store.save_run(
            Run(id=f"run-{event_id}", task_id=task_id, project_id=project, role_id="developer",
                workflow_step="develop", agent_backend="claude_code", status="completed")
        )
        self.store.save_event(
            Event(id=event_id, run_id=f"run-{event_id}", task_id=task_id, project_id=project,
                  event_type="agent.message", timestamp=stamp, payload={"text": event_id})
        )

    def ids(self, messages) -> list[str]:
        return [message["event_id"] for message in messages]

    def test_a_new_listener_gets_the_recent_events_of_every_sprint_in_order(self) -> None:
        messages = self.api.list_project_stream_messages("p1")

        self.assertEqual(self.ids(messages), ["e1", "e2", "e3"])
        self.assertEqual(messages[0]["payload"]["type"], "event")
        self.assertEqual(messages[0]["payload"]["event"]["project_id"], "p1")

    def test_a_cursor_resumes_after_that_event_and_other_projects_stay_out(self) -> None:
        self.assertEqual(
            self.ids(self.api.list_project_stream_messages("p1", after_event_id="e1")),
            ["e2", "e3"],
        )
        self.assertEqual(self.api.list_project_stream_messages("p1", after_event_id="e3"), [])

    def test_a_cursor_that_no_longer_exists_starts_over(self) -> None:
        messages = self.api.list_project_stream_messages("p1", after_event_id="pruned-long-ago")

        self.assertEqual(self.ids(messages), ["e1", "e2", "e3"])

    def test_the_limit_keeps_the_newest_events(self) -> None:
        self.assertEqual(
            self.ids(self.api.list_project_stream_messages("p1", limit=2)), ["e2", "e3"]
        )

    def test_an_unknown_project_is_a_404_before_any_stream_starts(self) -> None:
        app = create_dashboard_app(self.db_path)

        async def call():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.get("/api/v1/projects/nope/stream")

        response = asyncio.run(call())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")

    def test_the_stream_sends_each_event_once_with_its_id_then_stops_when_the_client_leaves(self) -> None:
        class _Request:
            headers: dict[str, str] = {}

            def __init__(self) -> None:
                self.checks = 0

            async def is_disconnected(self) -> bool:
                self.checks += 1
                return self.checks > 1

        context = ApiContext(db_path=self.db_path, manager_enabled=True)

        async def collect() -> list[bytes]:
            response = event_stream_response(
                context,
                _Request(),  # type: ignore[arg-type]
                after="e1",
                next_messages=lambda api, last: api.list_project_stream_messages(
                    "p1", after_event_id=last
                ),
            )
            with mock.patch("foreman.dashboard.streaming.STREAM_POLL_INTERVAL_SECONDS", 0):
                return [chunk async for chunk in response.body_iterator]

        chunks = asyncio.run(collect())
        text = b"".join(chunks).decode()

        self.assertTrue(text.startswith("retry: 1000"))
        self.assertEqual(text.count("id: e2\n"), 1)
        self.assertEqual(text.count("id: e3\n"), 1)
        self.assertNotIn("id: e1\n", text)
        self.assertNotIn("id: ex\n", text)


if __name__ == "__main__":
    unittest.main()
