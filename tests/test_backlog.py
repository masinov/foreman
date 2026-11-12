"""The backlog API under /api/v1 and `foreman backlog` (ADR-0021)."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from foreman.cli import main
from foreman.dashboard.app import create_dashboard_app
from foreman.models import Project, Sprint, Task
from foreman.mutations import Mutations
from foreman.store import ForemanStore


class BacklogCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = str(Path(self._temp.name) / "foreman.db")
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = Project(
            id="p1", name="P", repo_path=self._temp.name, workflow_id="development"
        )
        self.store.save_project(self.project)
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="Sprint 1", status="active"))
        self.store.save_sprint(Sprint(id="s2", project_id="p1", title="Sprint 2", status="planned"))

    def file(self, title: str, *, accept: bool = False) -> Task:
        task = Mutations(self.store, via="cli").file_task(self.project, title=title).task
        if accept:
            task = Mutations(self.store, via="cli").accept_task(task)
        return task


class BacklogApiTests(BacklogCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = create_dashboard_app(self.db_path, auth_token=None)

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async def call():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(call())

    def test_list_shows_filed_first_then_accepted_and_hides_declined(self) -> None:
        accepted = self.file("Accepted work", accept=True)
        filed = self.file("Filed work")
        declined = Mutations(self.store, via="cli").decline_task(self.file("Nope"))

        body = self.request("GET", "/api/v1/projects/p1/backlog").json()

        self.assertEqual([t["id"] for t in body["tasks"]], [filed.id, accepted.id])
        self.assertEqual([t["state"] for t in body["tasks"]], ["filed", "accepted"])
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["counts"], {"filed": 1, "accepted": 1, "declined": 1})
        self.assertEqual(body["triage"], "human")
        self.assertEqual(body["backlog_id"], "p1-backlog")
        self.assertTrue(body["tasks"][0]["task_key"])

        declined_only = self.request("GET", "/api/v1/projects/p1/backlog?status=declined").json()
        self.assertEqual([t["id"] for t in declined_only["tasks"]], [declined.id])

    def test_list_filters_searches_and_pages(self) -> None:
        for index in range(5):
            self.file(f"Alpha {index}")
        self.file("Beta", accept=True)

        page = self.request("GET", "/api/v1/projects/p1/backlog?q=alpha&limit=2&offset=2").json()
        self.assertEqual(page["total"], 5)
        self.assertEqual([t["title"] for t in page["tasks"]], ["Alpha 2", "Alpha 3"])

        accepted = self.request("GET", "/api/v1/projects/p1/backlog?status=accepted").json()
        self.assertEqual([t["title"] for t in accepted["tasks"]], ["Beta"])
        both = self.request("GET", "/api/v1/projects/p1/backlog?status=filed,accepted").json()
        self.assertEqual(both["total"], 6)

    def test_list_refuses_an_unknown_state_and_an_unknown_project(self) -> None:
        bad = self.request("GET", "/api/v1/projects/p1/backlog?status=planned")
        self.assertEqual((bad.status_code, bad.json()["code"]), (400, "invalid_request"))
        missing = self.request("GET", "/api/v1/projects/nope/backlog")
        self.assertEqual((missing.status_code, missing.json()["code"]), (404, "not_found"))

    def test_an_empty_backlog_lists_nothing(self) -> None:
        body = self.request("GET", "/api/v1/projects/p1/backlog").json()
        self.assertEqual((body["tasks"], body["total"], body["backlog_id"]), ([], 0, None))

    def test_filing_through_the_api(self) -> None:
        response = self.request(
            "POST",
            "/api/v1/projects/p1/backlog",
            json={"title": "From the page", "task_type": "fix", "requested_by": "ana"},
        )

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual((body["status"], body["in_backlog"]), ("triage", True))
        filed = [
            e for e in self.store.list_events(task_id=body["id"])
            if e.event_type == "backlog.task_filed"
        ]
        self.assertEqual((filed[0].payload["via"], filed[0].payload["by"]), ("dashboard", "ana"))

        accepted = self.request(
            "POST", "/api/v1/projects/p1/backlog", json={"title": "Mine", "accept": True}
        ).json()
        self.assertEqual(accepted["status"], "todo")

        bad = self.request("POST", "/api/v1/projects/p1/backlog", json={"title": " "})
        self.assertEqual(bad.status_code, 400)

    def test_accept_still_works_and_decline_through_the_api(self) -> None:
        first, second = self.file("One"), self.file("Two")

        accepted = self.request("POST", f"/api/v1/tasks/{first.id}/accept")
        self.assertEqual((accepted.status_code, accepted.json()["status"]), (200, "todo"))
        self.assertTrue(accepted.json()["in_backlog"])

        declined = self.request(
            "POST", f"/api/v1/tasks/{second.id}/decline", json={"reason": "duplicate"}
        )
        self.assertEqual((declined.status_code, declined.json()["status"]), (200, "declined"))
        again = self.request("POST", f"/api/v1/tasks/{second.id}/decline")
        self.assertEqual(again.status_code, 400)

    def test_plan_into_an_existing_sprint_and_into_a_new_one(self) -> None:
        first, second = self.file("One", accept=True), self.file("Two", accept=True)

        existing = self.request(
            "POST",
            "/api/v1/projects/p1/backlog/plan",
            json={"task_ids": [first.id], "sprint_id": "s2"},
        )
        self.assertEqual(existing.status_code, 200, existing.text)
        self.assertEqual(
            (existing.json()["sprint"]["id"], existing.json()["created_sprint"]), ("s2", False)
        )
        self.assertEqual(self.store.get_task(first.id).sprint_id, "s2")

        created = self.request(
            "POST",
            "/api/v1/projects/p1/backlog/plan",
            json={"task_ids": [second.id], "new_sprint": {"title": "Sprint 3", "goal": "Later"}},
        ).json()
        self.assertTrue(created["created_sprint"])
        self.assertEqual(
            (created["sprint"]["title"], created["sprint"]["status"]), ("Sprint 3", "planned")
        )
        self.assertEqual(self.store.get_task(second.id).sprint_id, created["sprint"]["id"])

    def test_plan_refusals(self) -> None:
        filed = self.file("Not accepted")
        accepted = self.file("Accepted", accept=True)
        self.store.save_sprint(Sprint(id="old", project_id="p1", title="Old", status="completed"))
        cases = (
            ({"task_ids": [filed.id], "sprint_id": "s2"}, 400),
            ({"task_ids": [accepted.id], "sprint_id": "old"}, 400),
            ({"task_ids": [accepted.id], "sprint_id": "p1-backlog"}, 404),
            ({"task_ids": [accepted.id]}, 400),
            ({"task_ids": [], "sprint_id": "s2"}, 400),
            ({"task_ids": ["missing"], "sprint_id": "s2"}, 404),
        )
        for body, status in cases:
            with self.subTest(body=body):
                response = self.request("POST", "/api/v1/projects/p1/backlog/plan", json=body)
                self.assertEqual(response.status_code, status, response.text)
        self.assertTrue(self.store.get_sprint(self.store.get_task(accepted.id).sprint_id).is_backlog)

    def test_unplan_moves_a_task_back(self) -> None:
        task = Task(id="queued", sprint_id="s2", project_id="p1", title="Queued")
        self.store.save_task(task)

        response = self.request("POST", "/api/v1/tasks/queued/unplan")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["in_backlog"])

    def test_sprint_endpoints_do_not_list_or_serve_the_backlog(self) -> None:
        self.file("Waiting")

        sprints = self.request("GET", "/api/v1/projects/p1/sprints").json()
        self.assertEqual([s["id"] for s in sprints["sprints"]], ["s1", "s2"])
        self.assertEqual(sprints["total"], 2)
        planned = self.request("GET", "/api/v1/projects/p1/sprints?status=planned").json()
        self.assertEqual([s["id"] for s in planned["sprints"]], ["s2"])
        self.assertEqual(self.request("GET", "/api/v1/sprints/p1-backlog").status_code, 404)
        self.assertEqual(
            self.request(
                "POST", "/api/v1/sprints/p1-backlog/tasks", json={"title": "Sneak in"}
            ).status_code,
            404,
        )
        for target in ("active", "completed"):
            self.assertEqual(
                self.request(
                    "PATCH", "/api/v1/sprints/p1-backlog", json={"status": target}
                ).status_code,
                400,
            )
        self.assertEqual(self.request("DELETE", "/api/v1/sprints/p1-backlog").status_code, 400)
        self.assertEqual(self.store.get_backlog("p1").status, "planned")

    def test_the_workspace_counts_the_backlog(self) -> None:
        self.file("One")
        self.file("Two", accept=True)
        Mutations(self.store, via="cli").decline_task(self.file("Three"))

        (entry,) = self.request("GET", "/api/v1/workspace").json()["projects"]
        self.assertEqual(entry["backlog"], 2)


class BacklogCliTests(BacklogCase):
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*argv, "--db", self.db_path])
        return code, out.getvalue(), err.getvalue()

    def test_add_list_accept_decline_plan_and_unplan(self) -> None:
        code, out, _ = self.run_cli("backlog", "add", "p1", "--title", "First", "--type", "fix")
        self.assertEqual(code, 0)
        self.assertIn("filed, not accepted", out)
        code, out, _ = self.run_cli("backlog", "add", "p1", "--title", "Second", "--accept")
        self.assertIn("accepted, not planned", out)
        code, out, _ = self.run_cli("backlog", "add", "p1", "--title", "Third")

        code, out, _ = self.run_cli("backlog", "list", "p1", "--json")
        self.assertEqual(code, 0)
        page = json.loads(out)
        self.assertEqual([t["title"] for t in page["tasks"]], ["First", "Third", "Second"])
        first, third, second = (t["id"] for t in page["tasks"])
        filed = self.store.list_events(task_id=first)
        self.assertEqual({e.payload.get("via") for e in filed if e.event_type == "backlog.task_filed"}, {"cli"})

        code, out, _ = self.run_cli("backlog", "list", "p1")
        self.assertIn("Filed, not accepted (2)", out)
        self.assertIn("Accepted, not planned (1)", out)

        self.assertEqual(self.run_cli("backlog", "accept", first)[0], 0)
        self.assertEqual(self.store.get_task(first).status, "todo")
        self.assertEqual(self.run_cli("backlog", "decline", third, "--reason", "dup")[0], 0)
        self.assertEqual(self.store.get_task(third).status, "declined")
        code, out, _ = self.run_cli("backlog", "list", "p1", "--status", "declined", "--json")
        self.assertEqual([t["id"] for t in json.loads(out)["tasks"]], [third])

        code, out, _ = self.run_cli("backlog", "plan", "p1", first, "--sprint", "s2")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.store.get_task(first).sprint_id, "s2")
        code, out, _ = self.run_cli(
            "backlog", "plan", "p1", second, "--new-sprint", "Sprint 3", "--goal", "Later"
        )
        self.assertEqual(code, 0)
        self.assertIn("(new)", out)
        new_sprint = self.store.get_sprint(self.store.get_task(second).sprint_id)
        self.assertEqual((new_sprint.title, new_sprint.status), ("Sprint 3", "planned"))

        self.assertEqual(self.run_cli("backlog", "unplan", first)[0], 0)
        self.assertTrue(self.store.get_sprint(self.store.get_task(first).sprint_id).is_backlog)

    def test_refusals_are_reported_and_change_nothing(self) -> None:
        filed = self.file("Not accepted")

        code, _, err = self.run_cli("backlog", "plan", "p1", filed.id, "--sprint", "s2")
        self.assertEqual(code, 1)
        self.assertIn("accept it before planning", err)
        code, _, err = self.run_cli("backlog", "list", "p1", "--status", "bogus")
        self.assertEqual(code, 1)
        code, _, err = self.run_cli(
            "task", "add", "p1", "--title", "T", "--criteria", "c", "--sprint", "p1-backlog"
        )
        self.assertEqual(code, 1)
        self.assertIn("is the backlog", err)
        code, _, err = self.run_cli("sprint", "activate", "p1-backlog")
        self.assertEqual(code, 1)
        self.assertEqual(self.store.get_task(filed.id).status, "triage")

    def test_sprint_list_does_not_show_the_backlog(self) -> None:
        self.file("Waiting")

        code, out, _ = self.run_cli("sprint", "list", "p1", "--json")

        self.assertEqual(code, 0)
        self.assertNotIn("p1-backlog", out)
        self.assertIn("s2", out)


if __name__ == "__main__":
    unittest.main()
