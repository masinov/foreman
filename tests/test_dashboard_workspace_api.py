"""The workspace, needs-you, milestone and paged sprint reads (sprint 58)."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3
import tempfile
import unittest

import httpx

from foreman.api.app import create_dashboard_app
from foreman.domain.models import (
    CompletionEvidence,
    DecisionGate,
    Event,
    Project,
    Run,
    Sprint,
    Task,
)
from foreman.store import ForemanStore

from plan_workflow import PLAN_WORKFLOW, install_plan_workflow

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
        if workflow == PLAN_WORKFLOW:
            install_plan_workflow(self.store, pid)

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

    def event(self, eid: str, tid: str, pid: str, etype: str, stamp: str,
              payload: dict | None = None) -> None:
        rid = f"run-{eid}"
        self.add_run(rid, tid, pid, completed_at=stamp)
        self.store.save_event(
            Event(id=eid, run_id=rid, task_id=tid, project_id=pid, event_type=etype,
                  timestamp=stamp, payload=payload or {})
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
        # A blocked task says why it is blocked and at which step it stopped.
        self.assertEqual(body["items"][0]["blocked"], {"reason": "Loop limit", "step": "develop"})
        self.assertNotIn("blocked", merge)
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


class SprintOrderNeedsYouTests(WorkspaceApiCase):
    """A proposed sprint order is the fifth thing that waits for a person."""

    def seed(self) -> None:
        self.seed_attention()
        self.sprint("s1b", "p1", "Sprint 1b")
        self.store.save_decision_gate(DecisionGate(
            id="gate-1", project_id="p1", sprint_id="s1",
            conflict_description="Sprint 1b needs the schema from Sprint 1.",
            suggested_order=["s1", "s1b"], suggested_reason="Schema first.",
            raised_at="2026-01-01T00:00:05Z",
        ))
        self.store.save_decision_gate(DecisionGate(
            id="gate-old", project_id="p1", sprint_id="s1", conflict_description="Old.",
            status="rejected", raised_at="2026-01-01T00:00:06Z",
        ))

    def test_a_pending_gate_is_listed_with_its_proposal(self) -> None:
        self.seed()
        body = self.get("/api/v1/projects/p1/needs-you").json()
        self.assertEqual(body["total"], 3)
        item = body["items"][0]
        self.assertEqual((item["kind"], item["task_id"], item["task_title"]), ("settle_order", None, None))
        self.assertEqual((item["project_id"], item["sprint_id"], item["sprint_title"], item["since"]),
                         ("p1", "s1", "Sprint 1", "2026-01-01T00:00:05Z"))
        self.assertEqual(item["gate"], {
            "id": "gate-1",
            "conflict_description": "Sprint 1b needs the schema from Sprint 1.",
            "suggested_reason": "Schema first.",
            "suggested_order": [{"sprint_id": "s1", "title": "Sprint 1"},
                                {"sprint_id": "s1b", "title": "Sprint 1b"}],
        })
        self.assertEqual(self.get("/api/v1/needs-you").json()["total"], 5)

    def test_it_counts_on_the_workspace(self) -> None:
        self.seed()
        p1 = next(p for p in self.get("/api/v1/workspace").json()["projects"] if p["id"] == "p1")
        self.assertEqual(p1["needs_you"], 3)  # filed work, a merge, and the gate
        self.assertEqual(p1["active_sprint"]["needs_you"], 3)

    def test_settling_it_removes_it(self) -> None:
        self.seed()

        async def patch():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.patch("/api/v1/gates/gate-1", json={"resolution": "accepted"})

        self.assertEqual(asyncio.run(patch()).status_code, 200)
        body = self.get("/api/v1/projects/p1/needs-you").json()
        self.assertEqual(body["total"], 2)
        self.assertNotIn("settle_order", [i["kind"] for i in body["items"]])
        self.assertEqual(self.store.get_sprint("s1b").order_index, 1)

    def test_the_query_count_does_not_grow_with_gates(self) -> None:
        self.seed()
        small = self.count_queries("/api/v1/needs-you")
        for i in range(20):
            self.store.save_decision_gate(DecisionGate(
                id=f"g{i}", project_id="p1", sprint_id="s1", conflict_description="c",
                suggested_order=["s1", "s1b"],
            ))
        self.assertEqual(self.count_queries("/api/v1/needs-you"), small)


class FinishSprintNeedsYouTests(WorkspaceApiCase):
    """A sprint whose every task is finished waits for a person to finish it
    (owner, 2026-11-24: the sprint page said "Ready to finish" and nothing led there)."""

    def seed(self, *, completion: str = "human") -> None:
        self.project("p1")
        project = self.store.get_project("p1")
        project.settings["sprint_completion"] = completion
        self.store.save_project(project)
        self.sprint("s1", "p1", "Sprint 1", status="active", started_at="2026-01-01T00:00:00Z")
        self.task("t1", "s1", "p1", status="done")
        self.task("t2", "s1", "p1", status="cancelled")

    def test_a_sprint_ready_to_finish_is_listed_with_its_tasks(self) -> None:
        self.seed()
        body = self.get("/api/v1/projects/p1/needs-you").json()
        self.assertEqual(body["total"], 1)
        item = body["items"][0]
        self.assertEqual(
            (item["kind"], item["sprint_id"], item["sprint_title"], item["task_id"]),
            ("finish_sprint", "s1", "Sprint 1", None),
        )
        self.assertEqual(item["task_counts"]["done"], 1)
        self.assertEqual(item["task_counts"]["cancelled"], 1)
        p1 = next(p for p in self.get("/api/v1/workspace").json()["projects"] if p["id"] == "p1")
        self.assertEqual(p1["needs_you"], 1)

    def test_not_while_a_task_is_open_nor_where_foreman_finishes_sprints(self) -> None:
        self.seed()
        self.task("t3", "s1", "p1", status="todo")
        self.assertEqual(self.get("/api/v1/projects/p1/needs-you").json()["total"], 0)

        # Every task finished again, but Foreman finishes this project's sprints.
        self.task("t3", "s1", "p1", status="done")
        project = self.store.get_project("p1")
        project.settings["sprint_completion"] = "auto"
        self.store.save_project(project)
        self.assertNotIn(
            "finish_sprint",
            [i["kind"] for i in self.get("/api/v1/projects/p1/needs-you").json()["items"]],
        )

    def test_since_is_when_foreman_recorded_it_ready(self) -> None:
        self.seed()
        sprint = self.store.get_sprint("s1")
        from foreman.history.records import RunRecords
        from foreman.notifications.delivery import NotificationDispatcher

        event = RunRecords(self.store, NotificationDispatcher(self.store)).emit_sprint_event(
            sprint, "engine.sprint_ready", {"sprint_id": "s1"}
        )
        item = self.get("/api/v1/projects/p1/needs-you").json()["items"][0]
        self.assertEqual(item["since"], event.timestamp)

    def test_the_query_count_does_not_grow_with_projects(self) -> None:
        self.seed()
        small = self.count_queries("/api/v1/needs-you")
        for n in range(2, 8):
            self.project(f"p{n}")
            self.sprint(f"s{n}", f"p{n}", f"Sprint {n}", status="active")
            self.task(f"t{n}", f"s{n}", f"p{n}", status="done")
        self.assertEqual(len(self.get("/api/v1/needs-you").json()["items"]), 7)
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
        self.event("merge-1", "t1", "p1", "engine.merge", "2026-01-02T00:00:00Z",
                   {"sha": "abc1234def5678"})
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
        # A project's milestones are its sprints' and its engine's; a merge is
        # its sprint's activity, not a milestone.
        self.assertEqual(
            self.kinds(body),
            [("engine_stopped", "ana"), ("engine_resumed", "bo"), ("engine_paused", "ana"),
             ("engine_started", None), ("sprint_started", None), ("sprint_finished", None),
             ("sprint_started", None)],
        )
        self.assertEqual(body["total"], 7)
        self.assertEqual(body["milestones"][0]["at"], "2026-01-07T00:00:01Z")
        self.assertEqual(body["milestones"][3]["at"], "2026-01-04T12:00:00Z")
        self.assertEqual(body["milestones"][4]["sprint_title"], "Sprint 2")
        self.assertNotIn("task_id", body["milestones"][0])
        # The backlog and an engine's rejected command are not milestones.
        self.assertNotIn("Backlog", {m["sprint_title"] for m in body["milestones"]})

    def test_a_finished_sprint_says_how_many_tasks_it_merged(self) -> None:
        self.seed()
        self.task("t2", "s1", "p1", "done")
        self.event("merge-2", "t2", "p1", "engine.merge", "2026-01-02T06:00:00Z")
        self.task("t3", "s1", "p1", "cancelled")
        body = self.get("/api/v1/projects/p1/milestones").json()
        by_kind = {m["kind"]: m for m in body["milestones"]}
        self.assertEqual(by_kind["sprint_finished"]["merged_count"], 2)
        self.assertIsNone(by_kind["sprint_started"]["merged_count"])

    def test_all_projects_orders_across_them(self) -> None:
        self.seed()
        body = self.get("/api/v1/milestones").json()
        self.assertEqual(body["total"], 10)
        stamps = [m["at"] for m in body["milestones"]]
        self.assertEqual(stamps[0], "2026-01-07T00:00:01Z")
        self.assertEqual(body["milestones"][-1]["at"], "2026-01-01T00:00:00+00:00")
        # An engine whose lease ran out, with nobody releasing it, was lost, at its expiry.
        lost = [m for m in body["milestones"] if m["kind"] == "engine_lost"]
        self.assertEqual([(m["project_id"], m["at"], m["actor"]) for m in lost],
                         [("p2", "2026-01-02T00:06:00Z", None)])
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
        self.assertEqual((page["total"], page["limit"], page["offset"]), (7, 3, 2))

    def test_a_confirmed_plan_names_who_confirmed_it_its_sprint_and_its_reason(self) -> None:
        self.seed()
        with self.store._connection:
            self.store._connection.execute(
                "INSERT INTO proposals (id, project_id, proposed_by, reason, operations_json, state,"
                " created_at, decided_by, decided_at) VALUES ('prop-1', 'p1', 'manager',"
                " 'Two tasks reach the goal.', '[{\"kind\": \"add_task\", \"sprint_id\": \"s2\"}]',"
                " 'confirmed', '2026-01-04T00:30:00Z', 'bo', '2026-01-04T00:40:00Z'),"
                " ('prop-2', 'p1', 'manager', 'Declined.', '[]', 'declined', '2026-01-04T00:30:00Z',"
                " 'bo', '2026-01-04T00:50:00Z')")
        body = self.get("/api/v1/projects/p1/milestones?kind=plan_confirmed").json()
        self.assertEqual([(m["actor"], m["sprint_id"], m["sprint_title"], m["detail"]) for m in body["milestones"]],
                         [("bo", "s2", "Sprint 2", "Two tasks reach the goal.")])

    def test_an_engine_starts_and_one_past_its_lease_was_lost(self) -> None:
        self.project("p1")
        with self.store._connection:
            self.store._connection.execute(
                "INSERT INTO leases (id, project_id, resource_type, resource_id, holder_id, lease_token,"
                " status, acquired_at, heartbeat_at, expires_at) VALUES"
                " ('gone','p1','engine','p1','eng-1','tok','active','2026-01-01T00:00:00Z',"
                "'2026-01-01T00:01:00Z','2026-01-01T00:06:00Z'),"
                " ('live','p1','engine','p1x','eng-2','tok2','active','2026-01-02T00:00:00Z',"
                "'2099-01-01T00:00:00Z','2099-01-01T00:05:00Z')"
            )
        body = self.get("/api/v1/projects/p1/milestones").json()
        self.assertEqual([(m["kind"], m["at"]) for m in body["milestones"]], [
            ("engine_started", "2026-01-02T00:00:00Z"),
            ("engine_lost", "2026-01-01T00:06:00Z"),
            ("engine_started", "2026-01-01T00:00:00Z"),
        ])

    def test_the_resume_that_starts_an_engine_names_who_started_it(self) -> None:
        # Start on the dashboard sends a resume that the new engine applies as it starts.
        self.project("p1")
        self.store.enqueue_engine_command(project_id="p1", command="resume", requested_by="ana", command_id="c-start")
        self.store.mark_engine_command("c-start", "completed")
        self.set_column("engine_commands", "requested_at", "2026-01-01T00:00:00Z", "c-start")
        self.set_column("engine_commands", "completed_at", "2026-01-01T00:00:02Z", "c-start")
        with self.store._connection:
            self.store._connection.execute(
                "INSERT INTO leases (id, project_id, resource_type, resource_id, holder_id, lease_token,"
                " status, acquired_at, heartbeat_at, expires_at, released_at) VALUES"
                " ('l1','p1','engine','p1','eng-1','tok','released','2026-01-01T00:00:01Z',"
                "'2026-01-01T00:10:00Z','2026-01-01T00:15:00Z','2026-01-01T00:10:00Z')"
            )
        body = self.get("/api/v1/projects/p1/milestones").json()
        self.assertEqual(self.kinds(body), [("engine_stopped", None), ("engine_started", "ana")])

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
        # A request in the backlog of a project where a person plans everything
        # does not wait for anyone (ADR-0028); it is counted as backlog work.
        self.assertEqual((p1["needs_you"], p1["backlog"]), (2, 2))
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
