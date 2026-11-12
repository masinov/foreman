"""Workspace settings reads and writes: session, machine, runners, tokens, channels."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import types
import unittest

import httpx

from foreman import __version__
from foreman.api_tokens import hash_token_secret
from foreman.dashboard.app import create_dashboard_app
from foreman.models import Project
from foreman.roles import load_roles
from foreman.runner.discovery import describe_runners
from foreman.store import ForemanStore

BASE = "/api/v1"


class AccessApiCase(unittest.TestCase):
    auth_token: str | None = None

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = str(Path(self._temp.name) / "foreman.db")
        self.store = ForemanStore(self.db_path)
        self.store.initialize()
        self.addCleanup(self.store.close)
        self.store.save_project(Project(id="alpha", name="Alpha", repo_path=self._temp.name, workflow_id="development"))
        self.store.save_project(Project(id="beta", name="Beta", repo_path=self._temp.name, workflow_id="development"))
        self.app = create_dashboard_app(self.db_path, auth_token=self.auth_token)

    def call(self, method: str, path: str, **kwargs) -> httpx.Response:
        async def run():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8123") as client:
                return await client.request(method, f"{BASE}{path}", **kwargs)

        return asyncio.run(run())


class SessionAndMachineTests(AccessApiCase):
    def test_no_authentication_reports_the_local_operator(self) -> None:
        body = self.call("GET", "/session").json()
        self.assertEqual(body["authentication"], "none")
        self.assertEqual(body["name"], "Local operator")
        self.assertFalse(body["can_sign_out"])
        self.assertIsNone(body["identity_provider"])

    def test_machine_reports_database_version_and_address(self) -> None:
        body = self.call("GET", "/machine").json()
        self.assertEqual(body["database_path"], self.db_path)
        self.assertEqual(body["version"], __version__)
        self.assertEqual(body["address"], "http://localhost:8123")


class TokenSessionTests(AccessApiCase):
    auth_token = "dash-secret"

    def test_a_dashboard_token_session_names_the_token_and_can_sign_out(self) -> None:
        self.assertEqual(self.call("GET", "/session").status_code, 401)
        body = self.call("GET", "/session", headers={"Authorization": "Bearer dash-secret"}).json()
        self.assertEqual(body["authentication"], "token")
        self.assertEqual(body["name"], "Dashboard token")
        self.assertTrue(body["can_sign_out"])

    def test_every_new_route_needs_the_dashboard_token(self) -> None:
        for method, path in (
            ("GET", "/tokens"),
            ("GET", "/runners"),
            ("GET", "/machine"),
            ("GET", "/notification-channels"),
            ("POST", "/projects/alpha/tokens"),
            ("POST", "/tokens/tok-x/revoke"),
            ("DELETE", "/notification-channels/dst-x"),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.call(method, path).status_code, 401)


class RunnerTests(AccessApiCase):
    def test_runners_come_from_the_runner_layer_and_the_roles(self) -> None:
        runners = {runner["id"]: runner for runner in self.call("GET", "/runners").json()["runners"]}
        self.assertEqual(set(runners), {"claude_code", "codex"})
        self.assertEqual(runners["claude_code"]["executable"], "claude")
        self.assertEqual(runners["codex"]["executable"], "codex")
        roles = load_roles().values()
        for backend_id, runner in runners.items():
            wanted = {
                model
                for role in roles
                if role.agent.backend == backend_id
                for model in (role.agent.model, *role.agent.model_ladder)
                if model
            }
            self.assertEqual(set(runner["models"]), wanted)

    def test_found_follows_the_path_lookup(self) -> None:
        role = types.SimpleNamespace(
            agent=types.SimpleNamespace(backend="codex", model="gpt-x", model_ladder=("gpt-x", "gpt-y"))
        )
        silent = types.SimpleNamespace(
            agent=types.SimpleNamespace(backend="claude_code", model="", model_ladder=())
        )
        runners = {
            runner["id"]: runner
            for runner in describe_runners(
                [role, silent], which=lambda name: "/usr/bin/codex" if name == "codex" else None
            )
        }
        self.assertTrue(runners["codex"]["found"])
        self.assertEqual(runners["codex"]["path"], "/usr/bin/codex")
        self.assertEqual(runners["codex"]["models"], ["gpt-x", "gpt-y"])
        self.assertFalse(runners["codex"]["uses_default"])
        self.assertFalse(runners["claude_code"]["found"])
        self.assertIsNone(runners["claude_code"]["path"])
        self.assertEqual(runners["claude_code"]["models"], [])
        self.assertTrue(runners["claude_code"]["uses_default"])


class TokenTests(AccessApiCase):
    def test_create_shows_the_secret_once_and_stores_only_its_hash(self) -> None:
        created = self.call("POST", "/projects/alpha/tokens", json={"name": "ci", "scopes": ["intake"]})
        self.assertEqual(created.status_code, 200)
        body = created.json()
        secret = body["secret"]
        self.assertTrue(secret.startswith("fmn_"))
        self.assertEqual(body["scopes"], ["intake"])
        self.assertEqual(body["project_name"], "Alpha")
        stored = self.store.get_api_token(body["id"])
        self.assertEqual(stored.token_hash, hash_token_secret(secret))
        self.assertEqual(stored.created_by, "dashboard")

        listed = self.call("GET", "/tokens")
        self.assertNotIn(secret, listed.text)
        self.assertNotIn("secret", listed.json()["tokens"][0])
        self.assertEqual(listed.json()["scopes"], ["intake"])

    def test_list_spans_projects_newest_first(self) -> None:
        self.store.create_api_token(project_id="alpha", name="old")
        self.store.create_api_token(project_id="beta", name="new")
        names = [token["name"] for token in self.call("GET", "/tokens").json()["tokens"]]
        self.assertEqual(names, ["new", "old"])

    def test_scopes_default_and_are_validated(self) -> None:
        default = self.call("POST", "/projects/alpha/tokens", json={"name": "x"})
        self.assertEqual(default.json()["scopes"], ["intake"])
        bad = self.call("POST", "/projects/alpha/tokens", json={"name": "y", "scopes": ["root"]})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["code"], "invalid_request")
        self.assertEqual(bad.json()["field"], "scopes")

    def test_a_token_needs_a_name_and_a_project(self) -> None:
        blank = self.call("POST", "/projects/alpha/tokens", json={"name": "  "})
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(blank.json()["field"], "name")
        missing = self.call("POST", "/projects/nope/tokens", json={"name": "x"})
        self.assertEqual(missing.status_code, 404)

    def test_revoke_marks_the_token_and_keeps_the_row(self) -> None:
        token, secret = self.store.create_api_token(project_id="alpha", name="ci")
        revoked = self.call("POST", f"/tokens/{token.id}/revoke")
        self.assertEqual(revoked.status_code, 200)
        self.assertFalse(revoked.json()["active"])
        self.assertIsNotNone(revoked.json()["revoked_at"])
        self.assertIsNone(self.store.find_api_token(secret))
        again = self.call("POST", f"/tokens/{token.id}/revoke")
        self.assertEqual(again.json()["revoked_at"], revoked.json()["revoked_at"])
        self.assertEqual(self.call("POST", "/tokens/tok-none/revoke").status_code, 404)


class ChannelTests(AccessApiCase):
    def test_empty_until_one_is_added(self) -> None:
        body = self.call("GET", "/notification-channels").json()
        self.assertEqual(body["channels"], [])
        self.assertEqual(body["kinds"], ["webhook"])

    def test_add_list_and_remove(self) -> None:
        added = self.call(
            "POST",
            "/projects/alpha/notification-channels",
            json={"name": "ops", "url": "https://example.test/hook", "secret_env": "OPS_KEY"},
        )
        self.assertEqual(added.status_code, 200)
        channel = added.json()
        self.assertEqual(channel["kind"], "webhook")
        self.assertTrue(channel["signed"])
        self.assertEqual(channel["project_name"], "Alpha")
        stored = self.store.get_notification_destination(channel["id"])
        self.assertEqual(stored.config, {"secret_env": "OPS_KEY"})

        listed = self.call("GET", "/notification-channels").json()["channels"]
        self.assertEqual([entry["name"] for entry in listed], ["ops"])
        self.assertNotIn("OPS_KEY", self.call("GET", "/notification-channels").text)

        removed = self.call("DELETE", f"/notification-channels/{channel['id']}")
        self.assertEqual(removed.json(), {"id": channel["id"], "removed": True})
        self.assertIsNone(self.store.get_notification_destination(channel["id"]))
        self.assertEqual(self.call("DELETE", f"/notification-channels/{channel['id']}").status_code, 404)

    def test_validation_matches_the_cli(self) -> None:
        url = "https://example.test/hook"
        self.call("POST", "/projects/alpha/notification-channels", json={"name": "ops", "url": url})
        duplicate = self.call("POST", "/projects/alpha/notification-channels", json={"name": "ops", "url": url})
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(duplicate.json()["field"], "name")
        same_name_elsewhere = self.call(
            "POST", "/projects/beta/notification-channels", json={"name": "ops", "url": url}
        )
        self.assertEqual(same_name_elsewhere.status_code, 200)
        bad_url = self.call("POST", "/projects/alpha/notification-channels", json={"name": "x", "url": "ftp://h"})
        self.assertEqual(bad_url.status_code, 400)
        self.assertEqual(bad_url.json()["field"], "url")
        blank = self.call("POST", "/projects/alpha/notification-channels", json={"name": " ", "url": url})
        self.assertEqual(blank.json()["field"], "name")
        kind = self.call(
            "POST", "/projects/alpha/notification-channels", json={"name": "k", "url": url, "kind": "pager"}
        )
        self.assertEqual(kind.status_code, 400)
        missing = self.call("POST", "/projects/nope/notification-channels", json={"name": "x", "url": url})
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
