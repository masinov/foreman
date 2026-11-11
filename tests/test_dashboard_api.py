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
from foreman.models import Project, Sprint, Task
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
            headers = {"Authorization": f"Bearer {token}"} if token else {}
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
        self.assertEqual(len(ROUTERS), 9)
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


if __name__ == "__main__":
    unittest.main()
