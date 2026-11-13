"""Moving a planned sprint up or down the queue (sprint 58)."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest

import httpx

from foreman.dashboard.app import create_dashboard_app
from foreman.models import Project, Sprint
from foreman.store import ForemanStore


class SprintQueueOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = str(Path(self._temp.name) / "foreman.db")
        self.store = ForemanStore(self.db_path)
        self.store.initialize()
        self.addCleanup(self.store.close)
        self.app = create_dashboard_app(self.db_path, auth_token=None)
        self.store.save_project(
            Project(id="p", name="P", repo_path=self._temp.name, workflow_id="development")
        )
        self.sprint("done", "completed", 0)
        self.sprint("active", "active", 1)
        self.sprint("a", "planned", 2)
        self.sprint("b", "planned", 3)
        self.sprint("c", "planned", 4)

    def sprint(self, sid: str, status: str, order: int) -> None:
        self.store.save_sprint(
            Sprint(id=sid, project_id="p", title=sid.title(), status=status, order_index=order)
        )

    def move(self, sprint_id: str, direction: str) -> httpx.Response:
        async def call():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.post(
                    f"/api/v1/sprints/{sprint_id}/move", json={"direction": direction}
                )

        return asyncio.run(call())

    def planned(self) -> list[str]:
        return [s.id for s in self.store.list_sprints("p") if s.status == "planned"]

    def test_up_and_down_swap_with_the_neighbour(self) -> None:
        response = self.move("c", "up")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["planned_order"], ["a", "c", "b"])
        self.assertEqual(self.planned(), ["a", "c", "b"])
        self.move("a", "down")
        self.assertEqual(self.planned(), ["c", "a", "b"])

    def test_the_ends_of_the_queue_stay_where_they_are(self) -> None:
        self.assertEqual(self.move("a", "up").status_code, 200)
        self.assertEqual(self.move("c", "down").status_code, 200)
        self.assertEqual(self.planned(), ["a", "b", "c"])

    def test_planned_sprints_stay_after_everything_else(self) -> None:
        self.move("b", "up")
        order = [s.id for s in self.store.list_sprints("p")]
        self.assertEqual(order, ["done", "active", "b", "a", "c"])

    def test_equal_order_numbers_are_repaired(self) -> None:
        for sid in ("a", "b", "c"):
            sprint = self.store.get_sprint(sid)
            sprint.order_index = 2
            self.store.save_sprint(sprint)
        before = self.planned()
        self.move(before[2], "up")
        self.assertEqual(self.planned(), [before[0], before[2], before[1]])

    def test_only_a_planned_sprint_moves_and_only_up_or_down(self) -> None:
        refused = self.move("active", "up")
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertIn("only a planned sprint", refused.text)
        self.assertEqual(self.move("a", "sideways").status_code, 400)
        self.assertEqual(self.move("missing", "up").status_code, 404)
        self.assertEqual(self.planned(), ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
