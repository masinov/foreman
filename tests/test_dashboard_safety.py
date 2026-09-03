"""Regression coverage for the sprint-53 dashboard minimum safety slice.

The dashboard binds to loopback by default, refuses a non-loopback bind
without a shared token, requires that token on every ``/api`` route once
configured, sends no cross-origin headers unless origins are allowlisted,
keeps the full-access manager chat loopback-only unless explicitly allowed,
validates repository paths on project creation, and bounds the events page.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from foreman.cli import build_parser
from foreman.dashboard_backend import create_dashboard_app
from foreman.dashboard_runtime import dashboard_security_policy, is_loopback_host
from foreman.dashboard_service import DashboardService, DashboardValidationError
from foreman.models import Project, Sprint
from foreman.store import ForemanStore


def _seed(db_path: Path, repo_path: str) -> None:
    with ForemanStore(db_path) as store:
        store.initialize()
        store.save_project(Project(id="p1", name="Safety", repo_path=repo_path, workflow_id="development"))
        store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))


def _request(app, method: str, url: str, **kwargs) -> httpx.Response:
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(send())


class TokenAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "foreman.db"
        _seed(self.db_path, self.temp.name)

    def test_api_requires_the_token_when_configured(self) -> None:
        app = create_dashboard_app(str(self.db_path), auth_token="s3cret")
        anonymous = _request(app, "GET", "/api/projects")
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(anonymous.headers.get("www-authenticate"), "Bearer")
        self.assertIn("token", anonymous.json()["error"].lower())

        wrong = _request(app, "GET", "/api/projects", headers={"Authorization": "Bearer nope"})
        self.assertEqual(wrong.status_code, 401)

        bearer = _request(app, "GET", "/api/projects", headers={"Authorization": "Bearer s3cret"})
        self.assertEqual(bearer.status_code, 200)
        header = _request(app, "GET", "/api/projects", headers={"X-Foreman-Token": "s3cret"})
        self.assertEqual(header.status_code, 200)
        query = _request(app, "GET", "/api/projects?token=s3cret")
        self.assertEqual(query.status_code, 200)

    def test_shell_and_assets_load_without_a_token(self) -> None:
        app = create_dashboard_app(str(self.db_path), auth_token="s3cret")
        shell = _request(app, "GET", "/dashboard")
        self.assertEqual(shell.status_code, 200)
        self.assertIn("<div id=\"root\">", shell.text)
        missing_asset = _request(app, "GET", "/assets/nope.js")
        self.assertEqual(missing_asset.status_code, 404)

    def test_no_token_means_open_api_for_loopback_use(self) -> None:
        app = create_dashboard_app(str(self.db_path))
        self.assertEqual(_request(app, "GET", "/api/projects").status_code, 200)


class CorsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "foreman.db"
        _seed(self.db_path, self.temp.name)

    def test_no_cross_origin_headers_by_default(self) -> None:
        app = create_dashboard_app(str(self.db_path))
        response = _request(app, "GET", "/api/projects", headers={"Origin": "http://evil.example"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("access-control-allow-origin"))

    def test_allowlisted_origin_gets_cors_headers(self) -> None:
        app = create_dashboard_app(str(self.db_path), allowed_origins=("http://localhost:5173",))
        allowed = _request(app, "GET", "/api/projects", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "http://localhost:5173")
        other = _request(app, "GET", "/api/projects", headers={"Origin": "http://evil.example"})
        self.assertIsNone(other.headers.get("access-control-allow-origin"))


class ManagerGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "foreman.db"
        _seed(self.db_path, self.temp.name)

    def test_manager_routes_are_forbidden_when_disabled(self) -> None:
        app = create_dashboard_app(str(self.db_path), manager_enabled=False)
        message = _request(app, "POST", "/api/projects/p1/meta/message", json={"message": "hi"})
        self.assertEqual(message.status_code, 403)
        self.assertIn("loopback", message.json()["error"])
        supervise = _request(app, "POST", "/api/projects/p1/meta/supervise", json={"event_id": "x"})
        self.assertEqual(supervise.status_code, 403)
        clear = _request(app, "DELETE", "/api/projects/p1/meta/session")
        self.assertEqual(clear.status_code, 403)
        history = _request(app, "GET", "/api/projects/p1/meta/history")
        self.assertEqual(history.status_code, 200)


class EventsLimitTests(unittest.TestCase):
    def test_events_page_size_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "foreman.db"
            _seed(db_path, tmp)
            app = create_dashboard_app(str(db_path))
            self.assertEqual(_request(app, "GET", "/api/sprints/s1/events?limit=0").status_code, 400)
            self.assertEqual(_request(app, "GET", "/api/sprints/s1/events?limit=999999").status_code, 200)


class SecurityPolicyTests(unittest.TestCase):
    def test_loopback_detection(self) -> None:
        for host in ("localhost", "127.0.0.1", "::1", "127.0.0.2"):
            self.assertTrue(is_loopback_host(host), host)
        for host in ("0.0.0.0", "192.168.1.10", "example.internal", "::"):
            self.assertFalse(is_loopback_host(host), host)

    def test_non_loopback_bind_requires_a_token(self) -> None:
        with self.assertRaises(RuntimeError) as raised:
            dashboard_security_policy("0.0.0.0", auth_token=None)
        self.assertIn("without a token", str(raised.exception))
        policy = dashboard_security_policy("0.0.0.0", auth_token="t")
        self.assertFalse(policy.manager_enabled)
        self.assertTrue(any("Manager chat disabled" in n for n in policy.notices))

    def test_explicit_opt_ins(self) -> None:
        insecure = dashboard_security_policy("0.0.0.0", auth_token=None, allow_insecure_network=True)
        self.assertIsNone(insecure.auth_token)
        self.assertTrue(any("WARNING" in n for n in insecure.notices))
        remote_manager = dashboard_security_policy("0.0.0.0", auth_token="t", allow_remote_manager=True)
        self.assertTrue(remote_manager.manager_enabled)
        local = dashboard_security_policy("localhost", auth_token=None)
        self.assertTrue(local.manager_enabled)
        self.assertEqual(local.notices, ())

    def test_cli_exposes_the_security_flags(self) -> None:
        args = build_parser().parse_args(
            ["dashboard", "--host", "0.0.0.0", "--token", "abc", "--allow-remote-manager", "--allowed-origin", "http://x"]
        )
        self.assertEqual(args.token, "abc")
        self.assertTrue(args.allow_remote_manager)
        self.assertFalse(args.allow_insecure_network)
        self.assertEqual(args.allowed_origins, ["http://x"])


class RepoPathValidationTests(unittest.TestCase):
    def test_create_project_rejects_missing_or_non_repo_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with ForemanStore(Path(tmp) / "foreman.db") as store:
                store.initialize()
                service = DashboardService(store)
                with self.assertRaises(DashboardValidationError):
                    service.create_project(name="Ghost", repo_path=str(Path(tmp) / "missing"), workflow_id="development")
                plain_dir = Path(tmp) / "plain"
                plain_dir.mkdir()
                with self.assertRaises(DashboardValidationError):
                    service.create_project(name="Plain", repo_path=str(plain_dir), workflow_id="development")
                repo_dir = Path(tmp) / "repo"
                (repo_dir / ".git").mkdir(parents=True)
                created = service.create_project(name="Real", repo_path=str(repo_dir), workflow_id="development")
                self.assertEqual(created["repo_path"], str(repo_dir))


if __name__ == "__main__":
    unittest.main()
