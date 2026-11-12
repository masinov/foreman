"""POST /api/v1/projects/{id}/engine/commands: pause, resume and stop a running engine."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest

import httpx

from foreman.dashboard.app import create_dashboard_app
from foreman.models import Project
from foreman.store import ForemanStore


class EngineCommandApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = str(Path(self._temp.name) / "foreman.db")
        self.store = ForemanStore(self.db_path)
        self.store.initialize()
        self.addCleanup(self.store.close)
        self.store.save_project(Project(id="p1", name="P1", repo_path=self._temp.name, workflow_id="development"))
        self.app = create_dashboard_app(self.db_path, auth_token=None)

    def post(self, path: str, body: dict) -> httpx.Response:
        async def call():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.post(path, json=body)

        return asyncio.run(call())

    def hold_engine(self) -> None:
        with self.store._connection:
            self.store._connection.execute(
                "INSERT INTO leases (id, project_id, resource_type, resource_id, holder_id, lease_token,"
                " status, acquired_at, heartbeat_at, expires_at) VALUES ('l','p1','engine','p1','e','t',"
                "'active','2026-01-01T00:00:00Z','2999-01-01T00:00:00Z','2999-01-01T00:00:00Z')"
            )

    def queued(self) -> list[str]:
        return [c.command for c in self.store.list_engine_commands("p1", limit=10)]

    def test_queues_each_steering_command_for_a_running_engine(self) -> None:
        self.hold_engine()
        for command in ("pause", "resume", "shutdown"):
            with self.subTest(command=command):
                response = self.post("/api/v1/projects/p1/engine/commands", {"command": command, "requested_by": "ana"})
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["command"]["command"], command)
                self.assertEqual(body["command"]["status"], "pending")
                self.assertEqual(body["requested_by"], "ana")
        self.assertEqual(sorted(self.queued()), ["pause", "resume", "shutdown"])

    def test_refuses_when_no_engine_is_running_and_queues_nothing(self) -> None:
        response = self.post("/api/v1/projects/p1/engine/commands", {"command": "shutdown"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"error": "The engine for p1 is not running, so there is nothing to stop.", "code": "invalid_request"},
        )
        self.assertEqual(self.queued(), [])

    def test_refuses_commands_that_are_not_steering(self) -> None:
        self.hold_engine()
        for command in ("run_task", "stop_task", "", "explode"):
            with self.subTest(command=command):
                response = self.post("/api/v1/projects/p1/engine/commands", {"command": command})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "invalid_request")
        self.assertEqual(self.queued(), [])

    def test_an_unknown_project_is_404(self) -> None:
        response = self.post("/api/v1/projects/nope/engine/commands", {"command": "pause"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")


if __name__ == "__main__":
    unittest.main()
