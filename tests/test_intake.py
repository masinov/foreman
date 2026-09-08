"""Tests for project API tokens and the intake endpoint.

Nothing here starts an agent: intake files a task and returns, so the suite
never reaches a real ``claude`` or ``codex`` binary.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

import httpx

from foreman.api_tokens import (
    INTAKE_SCOPE,
    TOKEN_PREFIX,
    ApiTokenError,
    hash_token_secret,
    looks_like_api_token,
    mint_token_secret,
    normalize_scopes,
)
from foreman.dashboard_backend import create_dashboard_app
from foreman.dashboard_service import (
    DashboardAuthError,
    DashboardPermissionError,
    DashboardService,
    DashboardValidationError,
)
from foreman.models import Project, Sprint
from foreman.store import ForemanStore

from tests.test_cli import cli_argv, cli_env


class ApiTokenSecretTests(unittest.TestCase):
    """The secret primitives: minting, hashing, and the scope vocabulary."""

    def test_minted_secrets_are_prefixed_and_unique(self) -> None:
        secrets = {mint_token_secret() for _ in range(50)}
        self.assertEqual(len(secrets), 50)
        for secret in secrets:
            self.assertTrue(secret.startswith(TOKEN_PREFIX))
            self.assertTrue(looks_like_api_token(secret))

    def test_hash_is_stable_sha256_hex(self) -> None:
        digest = hash_token_secret("fmn_example")
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, hash_token_secret("fmn_example"))
        self.assertNotEqual(digest, hash_token_secret("fmn_other"))

    def test_empty_secret_is_rejected(self) -> None:
        with self.assertRaises(ApiTokenError):
            hash_token_secret("   ")

    def test_scopes_default_to_intake_and_reject_unknown_values(self) -> None:
        self.assertEqual(normalize_scopes(None), (INTAKE_SCOPE,))
        self.assertEqual(normalize_scopes([]), (INTAKE_SCOPE,))
        self.assertEqual(normalize_scopes(["intake", "intake"]), (INTAKE_SCOPE,))
        with self.assertRaises(ApiTokenError):
            normalize_scopes(["admin"])

    def test_the_dashboard_token_is_not_mistaken_for_an_api_token(self) -> None:
        self.assertFalse(looks_like_api_token("dashboard-secret"))
        self.assertFalse(looks_like_api_token(None))
        self.assertFalse(looks_like_api_token(""))


class ApiTokenStoreTests(unittest.TestCase):
    """Create, find, and revoke tokens without ever persisting a secret."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(
            Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=self._tmp.name,
                workflow_id="development",
            )
        )

    def test_create_returns_a_record_and_a_one_time_secret(self) -> None:
        token, secret = self.store.create_api_token(
            project_id="project-1", name="pagerduty"
        )

        self.assertEqual(token.project_id, "project-1")
        self.assertEqual(token.name, "pagerduty")
        self.assertEqual(token.scopes, [INTAKE_SCOPE])
        self.assertTrue(token.is_active)
        self.assertIsNone(token.last_used_at)
        self.assertEqual(token.token_hash, hash_token_secret(secret))

    def test_only_the_hash_reaches_the_database_file(self) -> None:
        _, secret = self.store.create_api_token(project_id="project-1", name="ci")
        self.store.close()

        raw = self.db_path.read_bytes()
        self.assertNotIn(secret.encode("utf-8"), raw)
        self.assertIn(hash_token_secret(secret).encode("utf-8"), raw)

    def test_a_nameless_token_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.create_api_token(project_id="project-1", name="  ")

    def test_find_matches_the_secret_and_records_the_use(self) -> None:
        token, secret = self.store.create_api_token(
            project_id="project-1", name="pagerduty"
        )

        found = self.store.find_api_token(secret)

        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.id, token.id)
        self.assertIsNotNone(found.last_used_at)
        self.assertIsNotNone(self.store.get_api_token(token.id).last_used_at)

    def test_find_rejects_a_wrong_or_empty_secret(self) -> None:
        self.store.create_api_token(project_id="project-1", name="pagerduty")

        self.assertIsNone(self.store.find_api_token("fmn_not-a-real-secret"))
        self.assertIsNone(self.store.find_api_token(""))

    def test_revoked_tokens_stop_authenticating_but_stay_listed(self) -> None:
        token, secret = self.store.create_api_token(
            project_id="project-1", name="pagerduty"
        )

        revoked = self.store.revoke_api_token(token.id)

        self.assertIsNotNone(revoked)
        assert revoked is not None
        self.assertFalse(revoked.is_active)
        self.assertIsNone(self.store.find_api_token(secret))
        self.assertEqual([t.id for t in self.store.list_api_tokens("project-1")], [token.id])
        self.assertEqual(
            self.store.list_api_tokens("project-1", include_revoked=False), []
        )

    def test_revoking_twice_keeps_the_first_timestamp(self) -> None:
        token, _ = self.store.create_api_token(project_id="project-1", name="ci")
        first = self.store.revoke_api_token(token.id)
        assert first is not None

        second = self.store.revoke_api_token(token.id)

        assert second is not None
        self.assertEqual(second.revoked_at, first.revoked_at)

    def test_revoking_an_unknown_token_returns_none(self) -> None:
        self.assertIsNone(self.store.revoke_api_token("tok-missing"))

    def test_tokens_are_deleted_with_their_project(self) -> None:
        token, _ = self.store.create_api_token(project_id="project-1", name="ci")

        self.store._connection.execute("DELETE FROM projects WHERE id = 'project-1'")
        self.store._connection.commit()

        self.assertIsNone(self.store.get_api_token(token.id))


class IntakeMigrationTests(unittest.TestCase):
    """Migration 17 must reach a database that stopped at version 16."""

    def test_applies_cleanly_to_a_version_16_database(self) -> None:
        from foreman.migrations import MIGRATIONS
        from foreman.store import _SCHEMA_MIGRATIONS_DDL

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "old.db"
            connection = sqlite3.connect(db_path)
            connection.executescript(_SCHEMA_MIGRATIONS_DDL)
            for version, description, sql in MIGRATIONS:
                if version > 16:
                    continue
                connection.executescript(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version, description, applied_at) "
                    "VALUES (?, ?, datetime('now'))",
                    (version, description),
                )
            connection.commit()
            connection.close()

            with ForemanStore(db_path) as store:
                applied = store.migrate()

                self.assertIn(17, applied)
                self.assertEqual(store.schema_version(), 17)
                tables = {
                    row["name"]
                    for row in store._connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertIn("api_tokens", tables)
                columns = {
                    row["name"]
                    for row in store._connection.execute("PRAGMA table_info(tasks)")
                }
                self.assertLessEqual(
                    {"source_system", "source_ref", "source_url", "reporter"}, columns
                )

    def test_two_tokens_can_never_share_a_hash(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            store.save_project(
                Project(id="p", name="P", repo_path="/tmp", workflow_id="development")
            )
            token, _ = store.create_api_token(project_id="p", name="a")

            with self.assertRaises(sqlite3.IntegrityError):
                store._connection.execute(
                    "INSERT INTO api_tokens (id, project_id, name, token_hash, "
                    "scopes_json, created_by, created_at) "
                    "VALUES ('tok-dup', 'p', 'b', ?, '[\"intake\"]', 'human', 'now')",
                    (token.token_hash,),
                )


class IntakeServiceTests(unittest.TestCase):
    """`DashboardService.intake_task`: idempotency, the queue, and the audit trail."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(
            Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=self._tmp.name,
                workflow_id="development",
            )
        )
        self.api = DashboardService(self.store)
        self.token, self.secret = self.store.create_api_token(
            project_id="project-1", name="pagerduty"
        )

    def file(self, **overrides):
        payload = {
            "title": "Disk full on web-3",
            "source": {
                "system": "pagerduty",
                "external_ref": "INC-42",
                "url": "https://pd.example.com/INC-42",
                "reporter": "ana",
            },
        }
        payload.update(overrides)
        return self.api.intake_task("project-1", token=self.token, **payload)

    def test_a_new_reference_creates_a_task_carrying_its_source(self) -> None:
        result = self.file()

        self.assertTrue(result["created"])
        task = self.store.get_task(result["id"])
        assert task is not None
        self.assertEqual(task.source_system, "pagerduty")
        self.assertEqual(task.source_ref, "INC-42")
        self.assertEqual(task.source_url, "https://pd.example.com/INC-42")
        self.assertEqual(task.reporter, "ana")
        self.assertEqual(task.created_by, "api:pagerduty")
        # `triage` is the default policy: filed work waits for a person.
        self.assertEqual(task.status, "triage")
        self.assertEqual(task.task_type, "fix")

    def test_the_same_reference_returns_the_same_task_untouched(self) -> None:
        first = self.file()

        second = self.file(title="Disk full on web-3 (again)")

        self.assertFalse(second["created"])
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["title"], "Disk full on web-3")
        self.assertEqual(len(self.store.list_tasks(project_id="project-1")), 1)

    def test_a_different_reference_from_the_same_system_is_a_new_task(self) -> None:
        self.file()

        second = self.file(
            title="Disk full on web-4",
            source={"system": "pagerduty", "external_ref": "INC-43"},
        )

        self.assertTrue(second["created"])
        self.assertEqual(len(self.store.list_tasks(project_id="project-1")), 2)

    def test_without_an_idempotency_key_every_call_files_new_work(self) -> None:
        self.api.intake_task("project-1", token=self.token, title="Something broke")
        self.api.intake_task("project-1", token=self.token, title="Something broke")

        self.assertEqual(len(self.store.list_tasks(project_id="project-1")), 2)

    def test_the_intake_queue_is_created_active_when_no_sprint_is_running(self) -> None:
        result = self.file()

        sprint = self.store.get_sprint("project-1-intake")
        assert sprint is not None
        self.assertEqual(sprint.status, "active")
        self.assertEqual(sprint.title, "Intake queue")
        self.assertIsNotNone(sprint.started_at)
        self.assertEqual(self.store.get_task(result["id"]).sprint_id, sprint.id)

    def test_the_queue_is_planned_while_another_sprint_is_active(self) -> None:
        self.store.save_sprint(
            Sprint(id="sprint-1", project_id="project-1", title="S", status="active")
        )

        self.file()

        sprint = self.store.get_sprint("project-1-intake")
        assert sprint is not None
        self.assertEqual(sprint.status, "planned")

    def test_a_planned_queue_activates_once_the_active_sprint_finishes(self) -> None:
        self.store.save_sprint(
            Sprint(id="sprint-1", project_id="project-1", title="S", status="active")
        )
        self.file()
        self.api.transition_sprint("sprint-1", target_status="completed")

        self.file(source={"system": "pagerduty", "external_ref": "INC-99"})

        sprint = self.store.get_sprint("project-1-intake")
        assert sprint is not None
        self.assertEqual(sprint.status, "active")

    def test_an_explicit_sprint_is_used_instead_of_the_queue(self) -> None:
        self.store.save_sprint(
            Sprint(id="sprint-1", project_id="project-1", title="S", status="active")
        )

        result = self.file(sprint_id="sprint-1")

        self.assertEqual(self.store.get_task(result["id"]).sprint_id, "sprint-1")
        self.assertIsNone(self.store.get_sprint("project-1-intake"))

    def test_a_sprint_from_another_project_is_rejected(self) -> None:
        self.store.save_project(
            Project(
                id="project-2",
                name="Other",
                repo_path=self._tmp.name,
                workflow_id="development",
            )
        )
        self.store.save_sprint(
            Sprint(id="sprint-2", project_id="project-2", title="S", status="active")
        )

        with self.assertRaises(DashboardValidationError):
            self.file(sprint_id="sprint-2")

    def test_the_origin_is_recorded_as_an_event_without_the_secret(self) -> None:
        result = self.file()

        events = [
            event
            for event in self.store.list_events(task_id=result["id"])
            if event.event_type == "intake.task_created"
        ]
        self.assertEqual(len(events), 1)
        payload = events[0].payload
        self.assertEqual(payload["source"]["system"], "pagerduty")
        self.assertEqual(payload["source"]["external_ref"], "INC-42")
        self.assertEqual(payload["token_name"], "pagerduty")
        self.assertEqual(payload["token_id"], self.token.id)
        self.assertEqual(payload["created_by"], "api:pagerduty")
        self.assertNotIn(self.secret, json.dumps(payload))

        run = self.store.get_run(events[0].run_id)
        assert run is not None
        self.assertEqual(run.workflow_step, "intake")
        self.assertEqual(run.agent_backend, "api")

    def test_the_response_serializes_the_task_like_the_task_endpoint(self) -> None:
        result = self.file()

        detail = self.api.get_task(result["id"])
        detail["created"] = True
        self.assertEqual(result, detail)
        self.assertEqual(
            result["source"],
            {
                "system": "pagerduty",
                "external_ref": "INC-42",
                "url": "https://pd.example.com/INC-42",
                "reporter": "ana",
            },
        )

    def test_a_task_a_person_created_carries_no_source(self) -> None:
        self.store.save_sprint(
            Sprint(id="sprint-1", project_id="project-1", title="S", status="active")
        )
        created = self.api.create_task("sprint-1", title="Hand written")

        self.assertIsNone(self.api.get_task(created["id"])["source"])

    def test_bad_payloads_are_rejected_before_anything_is_written(self) -> None:
        cases = [
            {"title": "   "},
            {"title": "x", "task_type": "invention"},
            {"title": "x", "complexity": "enormous"},
            {"title": "x", "priority": "high"},
            {"title": "x", "source": {"system": "pd", "unexpected": "v"}},
            {"title": "x", "source": {"system": 7}},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(DashboardValidationError):
                    self.api.intake_task("project-1", token=self.token, **payload)
        self.assertEqual(self.store.list_tasks(project_id="project-1"), [])

    def test_authentication_separates_unknown_from_unauthorized(self) -> None:
        self.store.save_project(
            Project(
                id="project-2",
                name="Other",
                repo_path=self._tmp.name,
                workflow_id="development",
            )
        )
        _, other_secret = self.store.create_api_token(
            project_id="project-2", name="elsewhere"
        )

        with self.assertRaises(DashboardAuthError):
            self.api.authenticate_intake("project-1", None)
        with self.assertRaises(DashboardAuthError):
            self.api.authenticate_intake("project-1", "fmn_wrong")
        with self.assertRaises(DashboardPermissionError):
            self.api.authenticate_intake("project-1", other_secret)

        self.assertEqual(
            self.api.authenticate_intake("project-1", self.secret).id, self.token.id
        )

    def test_a_token_without_the_intake_scope_is_refused(self) -> None:
        # A token minted by a later version for some other scope. The scope
        # check must hold before that version exists, not after.
        secret = mint_token_secret()
        self.store._connection.execute(
            "INSERT INTO api_tokens (id, project_id, name, token_hash, scopes_json, "
            "created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "tok-scopeless",
                "project-1",
                "read-only",
                hash_token_secret(secret),
                json.dumps(["metrics"]),
                "human",
                "2026-01-01T00:00:00Z",
            ),
        )
        self.store._connection.commit()

        with self.assertRaises(DashboardPermissionError):
            self.api.authenticate_intake("project-1", secret)


class IntakeEndpointTests(unittest.TestCase):
    """`POST /api/projects/{id}/intake` and the credential the middleware allows."""

    DASHBOARD_TOKEN = "dashboard-secret"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        repo = Path(self._tmp.name) / "repo"
        (repo / ".git").mkdir(parents=True)
        self.db_path = Path(self._tmp.name) / "foreman.db"
        store = ForemanStore(self.db_path)
        store.initialize()
        for project_id, name in (("project-1", "Demo"), ("project-2", "Other")):
            store.save_project(
                Project(
                    id=project_id,
                    name=name,
                    repo_path=str(repo),
                    workflow_id="development",
                )
            )
        _, self.secret = store.create_api_token(project_id="project-1", name="pagerduty")
        _, self.other_secret = store.create_api_token(
            project_id="project-2", name="elsewhere"
        )
        self.revoked_token, self.revoked_secret = store.create_api_token(
            project_id="project-1", name="retired"
        )
        store.revoke_api_token(self.revoked_token.id)
        store.close()

        self.app = create_dashboard_app(str(self.db_path), auth_token=self.DASHBOARD_TOKEN)

    def request(self, method, path, *, token=None, json_body=None):
        async def _call():
            transport = httpx.ASGITransport(app=self.app)
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, path, headers=headers, json=json_body)

        return asyncio.run(_call())

    def post_intake(self, body, *, token=None, project="project-1"):
        return self.request(
            "POST", f"/api/projects/{project}/intake", token=token, json_body=body
        )

    BODY = {
        "title": "Disk full on web-3",
        "description": "The disk on web-3 is at 98%.",
        "acceptance_criteria": "Free space stays above 20%.",
        "source": {
            "system": "pagerduty",
            "external_ref": "INC-42",
            "url": "https://pd.example.com/INC-42",
            "reporter": "ana",
        },
    }

    def test_without_a_token_intake_is_401(self) -> None:
        response = self.post_intake(self.BODY)

        self.assertEqual(response.status_code, 401)
        self.assertIn("Unauthorized", response.json()["error"])

    def test_the_dashboard_token_is_not_accepted_on_intake(self) -> None:
        response = self.post_intake(self.BODY, token=self.DASHBOARD_TOKEN)

        self.assertEqual(response.status_code, 401)

    def test_a_revoked_token_is_401(self) -> None:
        response = self.post_intake(self.BODY, token=self.revoked_secret)

        self.assertEqual(response.status_code, 401)

    def test_a_token_from_another_project_is_403(self) -> None:
        response = self.post_intake(self.BODY, token=self.other_secret)

        self.assertEqual(response.status_code, 403)

    def test_first_call_is_201_and_a_repeat_is_200(self) -> None:
        first = self.post_intake(self.BODY, token=self.secret)

        self.assertEqual(first.status_code, 201)
        self.assertTrue(first.json()["created"])

        second = self.post_intake(self.BODY, token=self.secret)

        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(second.json()["id"], first.json()["id"])

    def test_the_response_carries_the_source_and_the_creating_token(self) -> None:
        payload = self.post_intake(self.BODY, token=self.secret).json()

        self.assertEqual(payload["source"]["system"], "pagerduty")
        self.assertEqual(payload["source"]["url"], "https://pd.example.com/INC-42")
        self.assertEqual(payload["created_by"], "api:pagerduty")
        self.assertEqual(payload["description"], "The disk on web-3 is at 98%.")
        self.assertEqual(payload["acceptance_criteria"], "Free space stays above 20%.")

    def test_a_missing_title_is_400(self) -> None:
        response = self.post_intake({"source": {"system": "ci"}}, token=self.secret)

        self.assertEqual(response.status_code, 400)

    def test_an_unknown_project_is_403_not_a_404_leak(self) -> None:
        # Authentication runs before existence: a caller whose token is not for
        # this project learns nothing about whether the project exists.
        response = self.post_intake(self.BODY, token=self.secret, project="nope")

        self.assertEqual(response.status_code, 403)

    def test_an_intake_token_is_refused_on_every_other_api_route(self) -> None:
        for method, path in (
            ("GET", "/api/projects"),
            ("GET", "/api/projects/project-1"),
            ("GET", "/api/roles"),
        ):
            with self.subTest(path=path):
                response = self.request(method, path, token=self.secret)

                self.assertEqual(response.status_code, 403)
                self.assertIn("intake", response.json()["error"])

    def test_the_dashboard_token_still_opens_the_other_routes(self) -> None:
        response = self.request("GET", "/api/projects", token=self.DASHBOARD_TOKEN)

        self.assertEqual(response.status_code, 200)

    def test_an_intake_token_is_refused_even_without_a_dashboard_token(self) -> None:
        open_app = create_dashboard_app(str(self.db_path), auth_token=None)

        async def _call():
            transport = httpx.ASGITransport(app=open_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get(
                    "/api/projects", headers={"Authorization": f"Bearer {self.secret}"}
                )

        self.assertEqual(asyncio.run(_call()).status_code, 403)


class TokenCliTests(unittest.TestCase):
    """`foreman token create|list|revoke`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(
            Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=self._tmp.name,
                workflow_id="development",
            )
        )

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cli_argv(*args), env=cli_env(), capture_output=True, text=True, check=False
        )

    def create_token(self, name: str = "pagerduty") -> tuple[str, str]:
        """Create a token through the CLI, returning its id and its secret."""

        result = self.run_cli(
            "token", "create", "project-1", "--name", name, "--db", str(self.db_path)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        secret = next(
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip().startswith(TOKEN_PREFIX)
        )
        token = self.store.list_api_tokens("project-1")[0]
        return token.id, secret

    def test_create_prints_the_secret_once_and_stores_only_its_hash(self) -> None:
        result = self.run_cli(
            "token", "create", "project-1", "--name", "pagerduty", "--db", str(self.db_path)
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("API token created", result.stdout)
        self.assertIn("shown once", result.stdout)
        secret = next(
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip().startswith(TOKEN_PREFIX)
        )
        token = self.store.list_api_tokens("project-1")[0]
        self.assertEqual(token.token_hash, hash_token_secret(secret))
        self.assertEqual(token.name, "pagerduty")
        self.assertEqual(token.scopes, [INTAKE_SCOPE])

    def test_create_needs_a_name(self) -> None:
        result = self.run_cli("token", "create", "project-1", "--db", str(self.db_path))

        self.assertNotEqual(result.returncode, 0)

    def test_create_rejects_an_unknown_scope(self) -> None:
        result = self.run_cli(
            "token", "create", "project-1", "--name", "x",
            "--scope", "admin", "--db", str(self.db_path),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.store.list_api_tokens("project-1"), [])

    def test_create_rejects_an_unknown_project(self) -> None:
        result = self.run_cli(
            "token", "create", "nope", "--name", "x", "--db", str(self.db_path)
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Unknown project", result.stderr)

    def test_list_shows_tokens_and_never_a_secret(self) -> None:
        token_id, secret = self.create_token()

        result = self.run_cli("token", "list", "project-1", "--db", str(self.db_path))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(token_id, result.stdout)
        self.assertIn("pagerduty", result.stdout)
        self.assertIn("scopes=intake", result.stdout)
        self.assertIn("last_used=never", result.stdout)
        self.assertNotIn(secret, result.stdout)

    def test_list_says_so_when_a_project_has_no_tokens(self) -> None:
        result = self.run_cli("token", "list", "project-1", "--db", str(self.db_path))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- none", result.stdout)

    def test_revoke_stops_the_token_from_authenticating(self) -> None:
        token_id, secret = self.create_token()

        result = self.run_cli(
            "token", "revoke", "project-1", token_id, "--db", str(self.db_path)
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("API token revoked", result.stdout)
        self.assertIsNone(self.store.find_api_token(secret))

    def test_revoke_refuses_a_token_from_another_project(self) -> None:
        token_id, secret = self.create_token()
        self.store.save_project(
            Project(
                id="project-2",
                name="Other",
                repo_path=self._tmp.name,
                workflow_id="development",
            )
        )

        result = self.run_cli(
            "token", "revoke", "project-2", token_id, "--db", str(self.db_path)
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Unknown API token", result.stderr)
        self.assertIsNotNone(self.store.find_api_token(secret))


if __name__ == "__main__":
    unittest.main()
