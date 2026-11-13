"""Block and unblock a task through the API (the task page's More menu)."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest

import httpx

from foreman.dashboard_backend import create_dashboard_app
from foreman.models import Project, Sprint, Task
from foreman.store import ForemanStore


class TaskBlockApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "foreman.db"
        store = ForemanStore(self.db_path)
        store.initialize()
        store.save_project(
            Project(
                id="proj",
                name="Project",
                repo_path=self.temp_dir.name,
                workflow_id="development",
            )
        )
        store.save_sprint(
            Sprint(id="sprint", project_id="proj", title="Sprint", status="active")
        )
        store.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _task(self, task_id: str, status: str, **fields) -> Task:
        store = ForemanStore(self.db_path)
        store.initialize()
        task = store.save_task(
            Task(
                id=task_id,
                sprint_id="sprint",
                project_id="proj",
                title=f"Task {task_id}",
                status=status,
                task_type="feature",
                created_at="2026-11-12T09:00:00+00:00",
                **fields,
            )
        )
        store.close()
        return task

    def _stored(self, task_id: str) -> Task:
        store = ForemanStore(self.db_path)
        store.initialize()
        try:
            return store.get_task(task_id)
        finally:
            store.close()

    def _event_types(self, task_id: str) -> list[str]:
        store = ForemanStore(self.db_path)
        store.initialize()
        try:
            return [event.event_type for event in store.list_events(task_id=task_id)]
        finally:
            store.close()

    def _post(self, url: str, body: dict | None = None) -> httpx.Response:
        async def send() -> httpx.Response:
            app = create_dashboard_app(str(self.db_path))
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.post(url, json=body if body is not None else {})

        return asyncio.run(send())

    def test_block_parks_the_task_with_the_reason(self) -> None:
        self._task("t1", "todo")

        response = self._post("/api/v1/tasks/t1/block", {"reason": "Waiting for the API key."})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["blocked_reason"], "Waiting for the API key.")
        self.assertEqual(payload["blocked_kind"], "engine")
        self.assertEqual(payload["created_at"], "2026-11-12T09:00:00+00:00")
        self.assertIn("human.task_blocked", self._event_types("t1"))

    def test_block_needs_a_reason(self) -> None:
        self._task("t1", "todo")

        response = self._post("/api/v1/tasks/t1/block", {"reason": "  "})

        self.assertEqual(response.status_code, 400)
        self.assertIn("why", response.json()["error"])
        self.assertEqual(self._stored("t1").status, "todo")

    def test_block_refuses_a_finished_task(self) -> None:
        self._task("t1", "done")

        response = self._post("/api/v1/tasks/t1/block", {"reason": "No."})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_request")
        self.assertEqual(self._stored("t1").status, "done")

    def test_unblock_returns_the_task_to_the_queue_with_guidance(self) -> None:
        self._task("t1", "blocked", blocked_reason="Tests failed three times.", workflow_current_step="test")

        response = self._post("/api/v1/tasks/t1/unblock", {"note": "Run the slow suite too."})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "todo")
        self.assertIsNone(payload["blocked_reason"])
        self.assertEqual([note["text"] for note in payload["guidance"]], ["Run the slow suite too."])
        self.assertFalse(payload["guidance"][0]["delivered"])
        self.assertIn("human.task_unblocked", self._event_types("t1"))

    def test_complete_marks_the_task_done_with_the_reason(self) -> None:
        self._task("t1", "in_progress", workflow_current_step="merge")

        response = self._post(
            "/api/v1/tasks/t1/complete", {"reason": "Merged by hand.", "requested_by": "alice"}
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "done")
        self.assertIsNone(response.json()["workflow_current_step"])
        closed = response.json()["closed_by_hand"]
        self.assertEqual((closed["reason"], closed["by"]), ("Merged by hand.", "alice"))
        self.assertIn("human.task_completed", self._event_types("t1"))

    def test_complete_needs_a_reason_and_unfinished_work(self) -> None:
        self._task("t1", "todo")
        self._task("t2", "cancelled")

        no_reason = self._post("/api/v1/tasks/t1/complete", {"reason": " "})
        finished = self._post("/api/v1/tasks/t2/complete", {"reason": "It is."})

        self.assertEqual(no_reason.status_code, 400)
        self.assertIn("why", no_reason.json()["error"])
        self.assertEqual(finished.status_code, 400)
        self.assertEqual(self._stored("t1").status, "todo")
        self.assertEqual(self._stored("t2").status, "cancelled")

    def test_reopen_returns_a_finished_task_to_the_queue(self) -> None:
        self._task("t1", "done", completed_at="2026-11-12T10:00:00+00:00")
        self._task("t2", "todo")

        reopened = self._post("/api/v1/tasks/t1/reopen")
        refused = self._post("/api/v1/tasks/t2/reopen")

        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(reopened.json()["status"], "todo")
        self.assertIsNone(reopened.json()["closed_by_hand"])
        self.assertIn("human.task_reopened", self._event_types("t1"))
        self.assertEqual(refused.status_code, 400)

    def test_unblock_without_a_note_records_no_guidance(self) -> None:
        self._task("t1", "blocked", blocked_reason="Parked.")

        response = self._post("/api/v1/tasks/t1/unblock")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["guidance"], [])

    def test_unblock_refuses_a_task_at_a_gate_and_records_nothing(self) -> None:
        self._task(
            "t1",
            "blocked",
            blocked_reason="Waiting for merge approval.",
            workflow_current_step="merge_approval",
        )

        response = self._post("/api/v1/tasks/t1/unblock", {"note": "Ignored."})

        self.assertEqual(response.status_code, 400)
        self.assertIn("gate", response.json()["error"])
        self.assertEqual(self._stored("t1").status, "blocked")
        self.assertNotIn("human.message", self._event_types("t1"))

    def test_unblock_refuses_a_task_that_is_not_blocked(self) -> None:
        self._task("t1", "todo")

        response = self._post("/api/v1/tasks/t1/unblock")

        self.assertEqual(response.status_code, 400)

    def test_unknown_task_is_not_found(self) -> None:
        self.assertEqual(self._post("/api/v1/tasks/nope/block", {"reason": "x"}).status_code, 404)
        self.assertEqual(self._post("/api/v1/tasks/nope/unblock").status_code, 404)


if __name__ == "__main__":
    unittest.main()
