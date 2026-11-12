"""The workspace, needs-you, milestone and paged sprint reads (sprint 58)."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3
import tempfile
import unittest

import httpx

from foreman.dashboard.app import create_dashboard_app
from foreman.models import CompletionEvidence, Event, Project, Run, Sprint, Task
from foreman.store import ForemanStore

ENGINE = "engine"


class WorkspaceApiCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = str(Path(self._temp.name) / "foreman.db")
        self.store = ForemanStore(self.db_path)
        self.store.initialize()
        self.addCleanup(self.store.close)
        self.app = create_dashboard_app(self.db_path, auth_token=None)

    def get(self, path: str) -> httpx.Response:
        async def call():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.get(path)

        return asyncio.run(call())

    # ── builders ─────────────────────────────────────────────────────────

    def project(self, pid: str, *, workflow: str = "development") -> None:
        self.store.save_project(
            Project(id=pid, name=f"Project {pid}", repo_path=self._temp.name, workflow_id=workflow)
        )

    def sprint(self, sid: str, pid: str, title: str, status: str = "planned", **kw) -> None:
        self.store.save_sprint(Sprint(id=sid, project_id=pid, title=title, status=status, **kw))

    def task(self, tid: str, sid: str, pid: str, status: str = "todo", **kw) -> Task:
        return self.store.save_task(
            Task(id=tid, sprint_id=sid, project_id=pid, title=f"Task {tid}", status=status, **kw)
        )

    def add_run(self, rid: str, tid: str, pid: str, *, cost: float = 0.0, status: str = "completed",
            completed_at: str | None = None) -> None:
        self.store.save_run(
            Run(id=rid, task_id=tid, project_id=pid, role_id="developer", workflow_step="develop",
                agent_backend="claude_code", status=status, cost_usd=cost, completed_at=completed_at,
                created_at=completed_at or "2026-01-01T00:00:00Z")
        )

    def event(self, eid: str, tid: str, pid: str, etype: str, stamp: str) -> None:
        rid = f"run-{eid}"
        self.add_run(rid, tid, pid, completed_at=stamp)
        self.store.save_event(
            Event(id=eid, run_id=rid, task_id=tid, project_id=pid, event_type=etype,
                  timestamp=stamp, payload={})
        )

    def seed_attention(self) -> None:
        self.project("p1")
        self.project("p2", workflow="development_with_architect")
        self.sprint("s1", "p1", "Sprint 1", "active")
        self.sprint("s2", "p2", "Sprint 2", "active")
        self.task("filed", "s1", "p1", "triage", created_at="2026-01-01T00:00:01Z")
        evidence = CompletionEvidence(
            task_id="merge", task_title="Task merge", acceptance_criteria="",
            tests_status="passed", tested_sha="abc123", head_sha="abc123",
            review_outcome="approved", reviewed_sha="abc123", proof_status="passed",
        )
        self.task("merge", "s1", "p1", "blocked", workflow_current_step="merge_approval",
                  blocked_reason="Awaiting human approval", completion_evidence=evidence)
        self.add_run("r-merge", "merge", "p1", completed_at="2026-01-01T00:00:03Z")
        self.task("plan", "s2", "p2", "blocked", workflow_current_step="human_approval",
                  blocked_reason="Awaiting human approval")
        self.add_run("r-plan", "plan", "p2", completed_at="2026-01-01T00:00:02Z")
        self.task("stuck", "s2", "p2", "blocked", workflow_current_step="develop",
                  blocked_reason="Loop limit")
        self.add_run("r-stuck", "stuck", "p2", completed_at="2026-01-01T00:00:04Z")
        self.task("fine", "s1", "p1", "todo")
        self.task("done", "s1", "p1", "done")


    def count_queries(self, path: str) -> int:
        statements: list[str] = []
        original = sqlite3.connect

        def traced(*args, **kwargs):
            connection = original(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        sqlite3.connect = traced
        try:
            self.assertEqual(self.get(path).status_code, 200)
        finally:
            sqlite3.connect = original
        selects = [s for s in statements if s.lstrip().upper().startswith(("SELECT", "WITH"))]
        self.assertGreater(len(selects), 0)
        return len(selects)

    def set_column(self, table: str, column: str, value: str, row_id: str) -> None:
        with self.store._connection:
            self.store._connection.execute(
                f"UPDATE {table} SET {column} = ? WHERE id = ?", (value, row_id)
            )


class NeedsYouTests(WorkspaceApiCase):
    def test_everything_waiting_for_a_person_newest_first(self) -> None:
        self.seed_attention()
        body = self.get("/api/v1/needs-you").json()
        self.assertEqual(body["total"], 4)
        self.assertEqual(
            [(i["task_id"], i["kind"]) for i in body["items"]],
            [("stuck", "unblock"), ("merge", "approve_merge"),
             ("plan", "approve_plan"), ("filed", "accept_filed_work")],
        )
        merge = body["items"][1]
        self.assertEqual(
            (merge["project_id"], merge["project_name"], merge["sprint_id"], merge["sprint_title"]),
            ("p1", "Project p1", "s1", "Sprint 1"),
        )
        self.assertTrue(merge["task_key"])
        self.assertEqual(merge["since"], "2026-01-01T00:00:03Z")
        self.assertEqual(
            merge["evidence"],
            {"tests_status": "passed", "tested_sha": "abc123", "review_outcome": "approved",
             "reviewed_sha": "abc123", "head_sha": "abc123", "proof_status": "passed"},
        )
        self.assertNotIn("evidence", body["items"][0])
        self.assertEqual(self.get("/api/needs-you").json(), body)

    def test_one_project_only(self) -> None:
        self.seed_attention()
        body = self.get("/api/v1/projects/p2/needs-you").json()
        self.assertEqual(body["total"], 2)
        self.assertEqual({i["project_id"] for i in body["items"]}, {"p2"})

    def test_nothing_waiting_is_an_empty_page(self) -> None:
        self.project("p1")
        self.sprint("s1", "p1", "Sprint 1", "active")
        self.task("t", "s1", "p1", "todo")
        body = self.get("/api/v1/needs-you").json()
        self.assertEqual((body["items"], body["total"]), ([], 0))
        self.assertEqual(self.get("/api/v1/projects/p1/needs-you").json()["items"], [])

    def test_paging_keeps_the_total(self) -> None:
        self.seed_attention()
        page = self.get("/api/v1/needs-you?limit=2&offset=1").json()
        self.assertEqual([i["task_id"] for i in page["items"]], ["merge", "plan"])
        self.assertEqual((page["total"], page["limit"], page["offset"]), (4, 2, 1))
        self.assertEqual(self.get("/api/v1/needs-you?offset=10").json()["items"], [])

    def test_bad_parameters_are_the_400_envelope(self) -> None:
        self.seed_attention()
        for query in ("limit=0", "limit=abc", "limit=100000", "offset=-1"):
            with self.subTest(query=query):
                response = self.get(f"/api/v1/needs-you?{query}")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "invalid_request")

    def test_an_unknown_project_is_404(self) -> None:
        response = self.get("/api/v1/projects/nope/needs-you")
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))

    def test_the_query_count_does_not_grow_with_tasks(self) -> None:
        self.seed_attention()
        small = self.count_queries("/api/v1/needs-you")
        for i in range(30):
            self.task(f"more-{i}", "s1", "p1", "triage")
        self.assertEqual(self.count_queries("/api/v1/needs-you"), small)


class MilestoneTests(WorkspaceApiCase):
    def seed(self) -> None:
        self.project("p1")
        self.project("p2")
        self.sprint("s1", "p1", "Sprint 1", "completed",
                    started_at="2026-01-01T00:00:00+00:00", completed_at="2026-01-03T00:00:00+00:00")
        self.sprint("s2", "p1", "Sprint 2", "active", started_at="2026-01-04T00:00:00Z")
        # The backlog is not a sprint (ADR-0021): it never starts or finishes.
        self.sprint("p1-backlog", "p1", "Backlog", "planned", kind="backlog",
                    started_at="2026-01-01T00:00:00Z")
        self.sprint("s3", "p2", "Sprint 3", "active", started_at="2026-01-02T12:00:00Z")
        self.task("t1", "s1", "p1", "done")
        self.event("merge-1", "t1", "p1", "engine.merge", "2026-01-02T00:00:00Z")
        self.event("noise", "t1", "p1", "engine.test_run", "2026-01-02T01:00:00Z")
        self.store.enqueue_engine_command(project_id="p1", command="pause", requested_by="ana", command_id="c-pause")
        self.store.mark_engine_command("c-pause", "completed")
        self.set_column("engine_commands", "completed_at", "2026-01-05T00:00:00Z", "c-pause")
        self.store.enqueue_engine_command(project_id="p1", command="resume", requested_by="bo", command_id="c-resume")
        self.store.mark_engine_command("c-resume", "completed")
        self.set_column("engine_commands", "completed_at", "2026-01-06T00:00:00Z", "c-resume")
        self.store.enqueue_engine_command(project_id="p1", command="shutdown", requested_by="ana", command_id="c-down")
        self.store.mark_engine_command("c-down", "completed")
        self.set_column("engine_commands", "completed_at", "2026-01-07T00:00:00Z", "c-down")
        self.store.enqueue_engine_command(project_id="p1", command="resume", requested_by="cy", command_id="c-lost")
        self.store.mark_engine_command("c-lost", "rejected")
        with self.store._connection:
            self.store._connection.execute(
                "INSERT INTO leases (id, project_id, resource_type, resource_id, holder_id, lease_token,"
                " status, acquired_at, heartbeat_at, expires_at, released_at) VALUES"
                " ('l1','p1','engine','p1','eng-1','tok','released','2026-01-04T12:00:00Z',"
                "'2026-01-07T00:00:00Z','2026-01-07T00:05:00Z','2026-01-07T00:00:01Z')"
            )
            self.store._connection.execute(
                "INSERT INTO leases (id, project_id, resource_type, resource_id, holder_id, lease_token,"
                " status, acquired_at, heartbeat_at, expires_at) VALUES"
                " ('l2','p2','engine','p2','eng-2','tok2','expired','2026-01-02T00:00:00Z',"
                "'2026-01-02T00:01:00Z','2026-01-02T00:06:00Z')"
            )

    def kinds(self, body: dict) -> list[tuple[str, str | None]]:
        return [(m["kind"], m["actor"]) for m in body["milestones"]]

    def test_every_kind_newest_first_with_who_when_known(self) -> None:
        self.seed()
        body = self.get("/api/v1/projects/p1/milestones").json()
        self.assertEqual(
            self.kinds(body),
            [("engine_stopped", "ana"), ("engine_resumed", "bo"), ("engine_paused", "ana"),
             ("engine_started", None), ("sprint_started", None), ("sprint_finished", None),
             ("task_merged", None), ("sprint_started", None)],
        )
        self.assertEqual(body["total"], 8)
        merged = body["milestones"][6]
        self.assertEqual((merged["task_id"], merged["sprint_id"], merged["sprint_title"]),
                         ("t1", "s1", "Sprint 1"))
        self.assertTrue(merged["task_key"])
        self.assertEqual(body["milestones"][4]["sprint_title"], "Sprint 2")
        # The backlog and an engine's rejected command are not milestones.
        self.assertNotIn("Backlog", {m["sprint_title"] for m in body["milestones"]})

    def test_all_projects_orders_across_them(self) -> None:
        self.seed()
        body = self.get("/api/v1/milestones").json()
        self.assertEqual(body["total"], 11)
        stamps = [m["at"] for m in body["milestones"]]
        self.assertEqual(stamps[0], "2026-01-07T00:00:01Z")
        self.assertEqual(body["milestones"][-1]["at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(
            {m["project_id"] for m in body["milestones"] if m["kind"] == "engine_stopped"}, {"p1", "p2"}
        )
        p2_stop = [m for m in body["milestones"] if m["project_id"] == "p2" and m["kind"] == "engine_stopped"][0]
        self.assertEqual((p2_stop["at"], p2_stop["actor"]), ("2026-01-02T00:06:00Z", None))
        self.assertEqual(self.get("/api/milestones").json(), body)

    def test_kind_filter_repeated_or_comma_separated(self) -> None:
        self.seed()
        repeated = self.get("/api/v1/projects/p1/milestones?kind=engine_paused&kind=engine_resumed").json()
        comma = self.get("/api/v1/projects/p1/milestones?kind=engine_paused,engine_resumed").json()
        self.assertEqual(repeated, comma)
        self.assertEqual(repeated["total"], 2)
        self.assertEqual(self.kinds(repeated), [("engine_resumed", "bo"), ("engine_paused", "ana")])

    def test_paging(self) -> None:
        self.seed()
        page = self.get("/api/v1/projects/p1/milestones?limit=3&offset=2").json()
        self.assertEqual(self.kinds(page), [("engine_paused", "ana"), ("engine_started", None), ("sprint_started", None)])
        self.assertEqual((page["total"], page["limit"], page["offset"]), (8, 3, 2))

    def test_empty_project(self) -> None:
        self.project("p1")
        body = self.get("/api/v1/projects/p1/milestones").json()
        self.assertEqual((body["milestones"], body["total"]), ([], 0))
        self.assertEqual(self.get("/api/v1/milestones").json()["total"], 0)

    def test_bad_parameters_are_the_400_envelope(self) -> None:
        self.seed()
        for path in ("/milestones?kind=bogus", "/projects/p1/milestones?kind=sprint_started,bogus",
                     "/milestones?limit=x", "/projects/p1/milestones?offset=-3"):
            with self.subTest(path=path):
                response = self.get(f"/api/v1{path}")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(set(response.json()), {"error", "code"})
                self.assertEqual(response.json()["code"], "invalid_request")

    def test_an_unknown_project_is_404(self) -> None:
        self.assertEqual(self.get("/api/v1/projects/nope/milestones").status_code, 404)


class WorkspaceTests(WorkspaceApiCase):
    def test_empty_workspace(self) -> None:
        self.assertEqual(self.get("/api/v1/workspace").json(), {"projects": []})

    def test_a_project_with_nothing_going_on(self) -> None:
        self.project("p1")
        (entry,) = self.get("/api/v1/workspace").json()["projects"]
        self.assertEqual(entry["engine"], {"state": "not_running", "task_id": None, "task_key": None,
                                           "task_title": None, "step": None})
        self.assertEqual((entry["active_sprint"], entry["needs_you"], entry["backlog"],
                          entry["latest_milestone"]), (None, 0, 0, None))
        self.assertEqual(
            (entry["id"], entry["name"], entry["default_branch"], entry["workflow_id"]),
            ("p1", "Project p1", "main", "development"),
        )
        self.assertEqual(entry["repo_path"], self._temp.name)

    def test_populated(self) -> None:
        self.seed_attention()
        self.sprint("p1-backlog", "p1", "Backlog", "planned", kind="backlog")
        self.task("q1", "p1-backlog", "p1", "triage")
        self.task("q2", "p1-backlog", "p1", "todo")
        self.task("q3", "p1-backlog", "p1", "declined")
        self.add_run("r-cost-1", "done", "p1", cost=1.25)
        self.add_run("r-cost-2", "merge", "p1", cost=0.5)
        self.add_run("r-cost-3", "q3", "p1", cost=9.0)
        self.add_run("r-live", "fine", "p1", status="running")
        with self.store._connection:
            self.store._connection.execute(
                "INSERT INTO leases (id, project_id, resource_type, resource_id, holder_id, lease_token,"
                " status, acquired_at, heartbeat_at, expires_at) VALUES ('l','p1','engine','p1','e','t',"
                "'active','2026-01-01T00:00:00Z','2999-01-01T00:00:00Z','2999-01-01T00:00:00Z')"
            )
        self.set_column("tasks", "workflow_current_step", "develop", "fine")
        projects = {p["id"]: p for p in self.get("/api/v1/workspace").json()["projects"]}
        p1, p2 = projects["p1"], projects["p2"]
        self.assertEqual(p1["engine"]["state"], "running")
        self.assertEqual((p1["engine"]["task_id"], p1["engine"]["step"]), ("fine", "develop"))
        self.assertEqual(p1["active_sprint"]["id"], "s1")
        self.assertEqual(p1["active_sprint"]["task_counts"]["blocked"], 1)
        self.assertEqual(p1["active_sprint"]["task_counts"]["triage"], 1)
        self.assertEqual(p1["active_sprint"]["needs_you"], 2)
        self.assertAlmostEqual(p1["active_sprint"]["spend_usd"], 1.75)
        self.assertEqual((p1["needs_you"], p1["backlog"]), (3, 2))  # the backlog's filed task counts too
        self.assertEqual(p2["engine"]["state"], "not_running")
        self.assertEqual((p2["needs_you"], p2["backlog"]), (2, 0))

    def test_a_paused_engine(self) -> None:
        self.project("p1")
        with self.store._connection:
            self.store._connection.execute(
                "INSERT INTO leases (id, project_id, resource_type, resource_id, holder_id, lease_token,"
                " status, acquired_at, heartbeat_at, expires_at) VALUES ('l','p1','engine','p1','e','t',"
                "'active','2026-01-01T00:00:00Z','2999-01-01T00:00:00Z','2999-01-01T00:00:00Z')"
            )
        self.store.enqueue_engine_command(project_id="p1", command="pause", requested_by="ana", command_id="c")
        self.store.mark_engine_command("c", "completed")
        (entry,) = self.get("/api/v1/workspace").json()["projects"]
        self.assertEqual(entry["engine"]["state"], "paused")
        self.assertEqual(entry["latest_milestone"]["kind"], "engine_paused")
        self.assertEqual(entry["latest_milestone"]["actor"], "ana")

    def test_the_query_count_does_not_grow_with_sprints_or_tasks(self) -> None:
        self.seed_attention()
        small = self.count_queries("/api/v1/workspace")
        for i in range(25):
            self.sprint(f"x{i}", "p1", f"Extra {i}", "completed")
            self.task(f"xt{i}", "s1", "p1", "blocked", workflow_current_step="develop")
            self.add_run(f"xr{i}", f"xt{i}", "p1", cost=1.0)
        self.assertEqual(self.count_queries("/api/v1/workspace"), small)
        # And it is a fixed number per project, not a number per task.
        self.project("p3")
        self.assertLessEqual(self.count_queries("/api/v1/workspace") - small, 8)


class SprintListTests(WorkspaceApiCase):
    def setUp(self) -> None:
        super().setUp()
        self.project("p1")
        self.project("p2")
        self.sprint("a", "p1", "Sprint 1: foundations", "completed", order_index=0)
        self.sprint("b", "p1", "Sprint 2: engine", "completed", order_index=1)
        self.sprint("c", "p1", "Sprint 10: dashboard", "active", order_index=2)
        self.sprint("d", "p1", "Later", "planned", order_index=3)
        self.sprint("e", "p1", "Dropped", "cancelled", order_index=4)
        self.sprint("z", "p2", "Sprint 1: other", "active")
        self.task("t", "c", "p1", "todo")

    def ids(self, query: str = "") -> list[str]:
        return [s["id"] for s in self.get(f"/api/v1/projects/p1/sprints{query}").json()["sprints"]]

    def test_without_parameters_every_sprint_in_order_as_before(self) -> None:
        body = self.get("/api/v1/projects/p1/sprints").json()
        self.assertEqual([s["id"] for s in body["sprints"]], ["a", "b", "c", "d", "e"])
        self.assertEqual(body["total"], 5)
        active = body["sprints"][2]
        self.assertEqual([t["id"] for t in active["tasks"]], ["t"])
        self.assertEqual(
            set(active), {"id", "project_id", "title", "goal", "status", "order_index", "started_at",
                          "completed_at", "task_counts", "totals", "tasks"},
        )

    def test_status_filter_repeated_or_comma_separated(self) -> None:
        self.assertEqual(self.ids("?status=completed"), ["a", "b"])
        self.assertEqual(self.ids("?status=active&status=planned"), ["c", "d"])
        self.assertEqual(self.ids("?status=active,planned"), ["c", "d"])

    def test_query_matches_number_or_title(self) -> None:
        self.assertEqual(self.ids("?q=10"), ["c"])
        self.assertEqual(self.ids("?q=ENGINE"), ["b"])
        self.assertEqual(self.ids("?q=sprint"), ["a", "b", "c"])
        self.assertEqual(self.ids("?q=nothing"), [])
        self.assertEqual(self.ids("?q=%25"), [])

    def test_paging_reports_the_total_of_the_filter(self) -> None:
        body = self.get("/api/v1/projects/p1/sprints?status=completed,active&limit=1&offset=1").json()
        self.assertEqual([s["id"] for s in body["sprints"]], ["b"])
        self.assertEqual(body["total"], 3)

    def test_recent_order_puts_the_latest_finished_first(self) -> None:
        # Finished out of queue order: the later-queued sprint finished first.
        self.sprint("a", "p1", "Sprint 1: foundations", "completed", order_index=0,
                    completed_at="2026-02-02T00:00:00Z")
        self.sprint("b", "p1", "Sprint 2: engine", "completed", order_index=1,
                    completed_at="2026-01-01T00:00:00Z")
        self.sprint("f", "p1", "Sprint 0: never stamped", "completed", order_index=5)
        self.assertEqual(self.ids("?status=completed&order=recent"), ["a", "b", "f"])
        self.assertEqual(self.ids("?status=completed&order=queue"), ["a", "b", "f"])
        body = self.get("/api/v1/projects/p1/sprints?status=completed&order=recent&limit=1&offset=1").json()
        self.assertEqual(([s["id"] for s in body["sprints"]], body["total"]), (["b"], 3))

    def test_empty_result(self) -> None:
        body = self.get("/api/v1/projects/p2/sprints?status=planned").json()
        self.assertEqual((body["sprints"], body["total"]), ([], 0))

    def test_bad_parameters_are_the_400_envelope(self) -> None:
        for query in ("status=done", "status=active,bogus", "limit=0", "limit=x", "offset=-1", "order=bogus"):
            with self.subTest(query=query):
                response = self.get(f"/api/v1/projects/p1/sprints?{query}")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "invalid_request")


class SprintPageReadTests(WorkspaceApiCase):
    """What the sprint page reads that no earlier slice needed."""

    def test_sprint_names_when_it_started_and_whether_foreman_picks_tasks(self) -> None:
        self.project("p1")
        self.sprint("s1", "p1", "One", "active", started_at="2026-11-11T09:00:00Z")
        body = self.get("/api/v1/sprints/s1").json()
        self.assertEqual(body["started_at"], "2026-11-11T09:00:00Z")
        self.assertIsNone(body["completed_at"])
        self.assertFalse(body["picks_own_tasks"])

        project = self.store.get_project("p1")
        project.settings = {"task_selection_mode": "autonomous"}
        self.store.save_project(project)
        self.assertTrue(self.get("/api/v1/sprints/s1").json()["picks_own_tasks"])

    def test_sprint_tasks_carry_checks_from_completion_evidence(self) -> None:
        self.project("p1")
        self.sprint("s1", "p1", "One", "active")
        evidence = CompletionEvidence(
            task_id="a", task_title="Task a", acceptance_criteria="",
            tests_status="passed", head_sha="abc123", review_outcome="approve",
        )
        self.task("a", "s1", "p1", "blocked", completion_evidence=evidence)
        self.task("b", "s1", "p1", "todo")
        tasks = {t["id"]: t for t in self.get("/api/v1/sprints/s1/tasks").json()["tasks"]}
        self.assertEqual(
            tasks["a"]["checks"], {"tests": "passed", "review": "approve", "commit": "abc123"}
        )
        self.assertIsNone(tasks["b"]["checks"])

    def test_sprint_events_filter_by_type(self) -> None:
        self.project("p1")
        self.sprint("s1", "p1", "One", "active")
        self.task("a", "s1", "p1", "in_progress")
        self.event("e1", "a", "p1", "agent.message", "2026-01-01T00:00:01Z")
        self.event("e2", "a", "p1", "workflow.step_completed", "2026-01-01T00:00:02Z")
        self.event("e3", "a", "p1", "agent.message", "2026-01-01T00:00:03Z")
        self.event("e4", "a", "p1", "workflow.step_completed", "2026-01-01T00:00:04Z")
        body = self.get("/api/v1/sprints/s1/events?type=workflow.step_completed&limit=1").json()
        self.assertEqual([e["id"] for e in body["events"]], ["e4"])
        self.assertTrue(body["has_more"])
        older = self.get(
            "/api/v1/sprints/s1/events?type=workflow.step_completed&limit=5&before=e4"
        ).json()
        self.assertEqual([e["id"] for e in older["events"]], ["e2"])
        everything = self.get("/api/v1/sprints/s1/events?limit=10").json()
        self.assertEqual(len(everything["events"]), 4)

    def test_project_workflow_lists_its_steps(self) -> None:
        self.project("p1")
        body = self.get("/api/v1/projects/p1/workflow").json()
        self.assertEqual(body["id"], "development")
        ids = [step["id"] for step in body["steps"]]
        self.assertIn("develop", ids)
        self.assertEqual(ids[-1], body["steps"][-1]["id"])
        self.assertEqual(self.get("/api/v1/projects/nope/workflow").status_code, 404)


if __name__ == "__main__":
    unittest.main()
