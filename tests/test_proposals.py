"""Proposals: the manager proposes, a person confirms (ADR-0022).

The service, the API under /api/v1, `foreman proposal`, and the refusal of
state changes from inside a manager session.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

from foreman.cli import main
from foreman.cli.parser import MANAGER_SESSION_COMMANDS
from foreman.dashboard.app import create_dashboard_app
from foreman.models import Project, Sprint, Task
from foreman.mutations import Mutations
from foreman.proposals import (
    MANAGER,
    OPERATION_KINDS,
    ProposalError,
    Proposals,
    normalize_operations,
)
from foreman.store import ForemanStore


class ProposalCase(unittest.TestCase):
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
        self.store.save_project(
            Project(id="p2", name="Other", repo_path=self._temp.name, workflow_id="development")
        )
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="Sprint 1", status="active"))
        self.store.save_sprint(Sprint(id="s2", project_id="p1", title="Sprint 2", status="planned"))
        self.store.save_sprint(Sprint(id="x1", project_id="p2", title="Elsewhere", status="planned"))
        self.proposals = Proposals(self.store, via="cli", actor="manager-test")

    def file(self, title: str, *, accept: bool = False) -> Task:
        task = Mutations(self.store, via="cli").file_task(self.project, title=title).task
        if accept:
            task = Mutations(self.store, via="cli").accept_task(task)
        return task

    def task(self, task_id: str, status: str, *, sprint: str = "s1", **fields) -> Task:
        task = Task(id=task_id, sprint_id=sprint, project_id="p1", title=task_id.upper(), status=status, **fields)
        return self.store.save_task(task)

    def gate_task(self, task_id: str = "g1") -> Task:
        return self.task(
            task_id,
            "blocked",
            blocked_reason="Waiting for merge approval.",
            workflow_current_step="merge_approval",
        )

    def propose(self, *operations, leaves=None, reason="Because.", proposed_by=MANAGER):
        return self.proposals.create(
            self.project,
            reason=reason,
            operations=list(operations),
            leaves=leaves,
            proposed_by=proposed_by,
        )

    def snapshot(self) -> dict:
        """Every row that a proposal could change, to show nothing changed."""

        connection = sqlite3.connect(self.db_path)
        try:
            return {
                table: connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                for table in ("sprints", "tasks", "runs", "events", "human_gate_decisions")
            }
        finally:
            connection.close()

    def count_proposals(self) -> int:
        return self.store.page_proposals("p1")[1]


class AtomicStoreTests(ProposalCase):
    def test_writes_inside_atomic_commit_together_or_not_at_all(self) -> None:
        with self.store.atomic():
            self.task("a", "todo")
            self.task("b", "todo")
        self.assertIsNotNone(self.store.get_task("b"))

        with self.assertRaises(RuntimeError):
            with self.store.atomic():
                self.task("c", "todo")
                raise RuntimeError("stop")
        self.assertIsNone(self.store.get_task("c"))

        with self.store.atomic(commit=False):
            self.task("d", "todo")
            self.assertIsNotNone(self.store.get_task("d"))
        self.assertIsNone(self.store.get_task("d"))
        # Writes outside a block commit on their own again.
        self.task("e", "todo")
        other = ForemanStore(self.db_path)
        self.addCleanup(other.close)
        self.assertIsNotNone(other.get_task("e"))


class CreateTests(ProposalCase):
    """Each operation kind is accepted when it is allowed now, and nothing changes."""

    def assert_proposed(self, *operations, leaves=None):
        before = self.snapshot()
        proposal = self.propose(*operations, leaves=leaves)
        self.assertEqual(proposal.state, "proposed")
        self.assertEqual(self.snapshot(), before, "creating a proposal changed the project")
        stored = self.store.get_proposal(proposal.id)
        self.assertEqual(stored.operations, proposal.operations)
        return stored

    def test_every_kind_is_accepted(self) -> None:
        filed = self.file("Filed")
        accepted = self.file("Accepted", accept=True)
        declinable = self.file("Declinable")
        self.task("todo1", "todo", sprint="s2")
        self.task("blocked1", "blocked", blocked_reason="Parked.")
        self.task("running", "in_progress")
        self.gate_task("g1")
        self.gate_task("g2")
        cases = {
            "create_sprint": {"kind": "create_sprint", "title": "Sprint 3", "goal": "Ship it."},
            "edit_sprint": {"kind": "edit_sprint", "sprint_id": "s2", "goal": "New goal."},
            "activate_sprint": None,
            "finish_sprint": None,
            "file_task": {"kind": "file_task", "title": "New work", "task_type": "fix", "accept": True},
            "accept_task": {"kind": "accept_task", "task_id": filed.id},
            "decline_task": {"kind": "decline_task", "task_id": declinable.id, "reason": "Out of scope."},
            "plan_tasks": {"kind": "plan_tasks", "task_ids": [accepted.id], "sprint_id": "s2"},
            "unplan_task": {"kind": "unplan_task", "task_id": "todo1"},
            "edit_task": {"kind": "edit_task", "task_id": "running", "title": "Renamed", "priority": 2},
            "block_task": {"kind": "block_task", "task_id": "running", "reason": "Wait for the spec."},
            "unblock_task": {"kind": "unblock_task", "task_id": "blocked1"},
            "cancel_task": {"kind": "cancel_task", "task_id": "todo1"},
            "send_back": {"kind": "send_back", "task_id": "g1", "guidance": "Report skipped tests too."},
            "approve_gate": {"kind": "approve_gate", "task_id": "g2"},
        }
        self.assertEqual(set(cases), set(OPERATION_KINDS))
        for kind, operation in cases.items():
            if operation is None:
                continue
            with self.subTest(kind=kind):
                self.assert_proposed(operation)

        # Sprint lifecycle: finishing s1 needs its tasks resolved, activating
        # s2 needs s1 out of the way. In order, both are allowed.
        for task in self.store.list_tasks(sprint_id="s1"):
            task.status = "done"
            self.store.save_task(task)
        self.assert_proposed(
            {"kind": "finish_sprint", "sprint_id": "s1"},
            {"kind": "activate_sprint", "sprint_id": "s2"},
        )

    def test_operations_are_judged_in_order_on_what_the_earlier_ones_did(self) -> None:
        filed = self.file("Filed")
        proposal = self.assert_proposed(
            {"kind": "accept_task", "task_id": filed.id},
            {"kind": "plan_tasks", "task_ids": [filed.id], "new_sprint": {"title": "Sprint 3"}},
            leaves=[self.file("Later").id],
        )
        self.assertEqual(self.store.get_task(filed.id).status, "triage")
        self.assertEqual(proposal.names["tasks"][filed.id]["title"], "Filed")
        self.assertEqual(len(proposal.leaves), 1)
        # In the other order the plan is refused: the task is not accepted yet.
        with self.assertRaisesRegex(ProposalError, "Operation 1 .*accept it before planning"):
            self.propose(
                {"kind": "plan_tasks", "task_ids": [filed.id], "sprint_id": "s2"},
                {"kind": "accept_task", "task_id": filed.id},
            )

    def test_the_proposer_and_turn_are_recorded(self) -> None:
        proposal = self.proposals.create(
            self.project,
            reason="Start Sprint 2.",
            operations=[{"kind": "edit_sprint", "sprint_id": "s2", "title": "Sprint two"}],
            proposed_by=MANAGER,
            session_id="sess-1",
            turn_id="turn-1",
        )
        stored = self.store.get_proposal(proposal.id)
        self.assertEqual(
            (stored.proposed_by, stored.session_id, stored.turn_id, stored.reason),
            (MANAGER, "sess-1", "turn-1", "Start Sprint 2."),
        )
        self.assertEqual([p.id for p in self.store.list_turn_proposals("turn-1")], [proposal.id])


class CreateRefusalTests(ProposalCase):
    """A refused operation is reported with its position and reason, and nothing is stored."""

    def assert_refused(self, pattern: str, *operations, leaves=None, reason="Because."):
        before = self.snapshot()
        with self.assertRaisesRegex(ProposalError, pattern):
            self.propose(*operations, leaves=leaves, reason=reason)
        self.assertEqual(self.count_proposals(), 0)
        self.assertEqual(self.snapshot(), before)

    def test_the_shape_is_checked(self) -> None:
        cases = [
            ("needs a reason", [{"kind": "create_sprint", "title": "X"}], "  "),
            ("at least one operation", [], "Why."),
            ("Operation 1: unknown kind 'merge_now'", [{"kind": "merge_now"}], "Why."),
            ("Operation 1 must be an object", ["create_sprint"], "Why."),
            ("unknown fields: colour", [{"kind": "create_sprint", "title": "X", "colour": "red"}], "Why."),
            ("title is required", [{"kind": "create_sprint"}], "Why."),
            ("title must be a non-empty string", [{"kind": "create_sprint", "title": " "}], "Why."),
            ("priority must be an integer", [{"kind": "edit_task", "task_id": "t", "priority": "high"}], "Why."),
            ("accept must be true or false", [{"kind": "file_task", "title": "X", "accept": "yes"}], "Why."),
            ("task_ids must be a non-empty list", [{"kind": "plan_tasks", "task_ids": [], "sprint_id": "s2"}], "Why."),
            ("exactly one of sprint_id or new_sprint", [{"kind": "plan_tasks", "task_ids": ["a"]}], "Why."),
            ("new_sprint.title", [{"kind": "plan_tasks", "task_ids": ["a"], "new_sprint": {}}], "Why."),
            ("at least one of title, goal", [{"kind": "edit_sprint", "sprint_id": "s2"}], "Why."),
            ("reason is required", [{"kind": "block_task", "task_id": "t"}], "Why."),
            ("guidance is required", [{"kind": "send_back", "task_id": "t"}], "Why."),
        ]
        for pattern, operations, reason in cases:
            with self.subTest(pattern=pattern):
                self.assert_refused(pattern, *operations, reason=reason)
        self.assert_refused("leaves: there is no task nope", {"kind": "create_sprint", "title": "X"}, leaves=["nope"])
        self.assertEqual(
            normalize_operations([{"kind": "create_sprint", "title": " X ", "goal": None}]),
            [{"kind": "create_sprint", "title": "X"}],
        )

    def test_what_is_named_must_exist_in_the_project(self) -> None:
        self.task("t1", "todo")
        self.assert_refused("Operation 2 \\(accept filed work\\): there is no task nope in project p1",
                            {"kind": "create_sprint", "title": "X"}, {"kind": "accept_task", "task_id": "nope"})
        self.assert_refused("there is no sprint x1 in project p1", {"kind": "activate_sprint", "sprint_id": "x1"})
        self.assert_refused("there is no sprint nope", {"kind": "plan_tasks", "task_ids": ["t1"], "sprint_id": "nope"})

    def test_each_kind_is_refused_when_it_is_not_allowed_now(self) -> None:
        self.task("done1", "done")
        self.task("todo1", "todo")
        self.task("running", "in_progress")
        filed = self.file("Filed")
        backlog_id = filed.sprint_id
        declined = Mutations(self.store, via="cli").decline_task(self.file("Gone"))
        cases = [
            # Creating a sprint has no state to be refused by; a blank title is
            # a shape refusal (above).
            ("create_sprint", None, None),
            ("edit_sprint", "backlog is not a sprint", {"kind": "edit_sprint", "sprint_id": backlog_id, "title": "B"}),
            ("activate_sprint", "already active", {"kind": "activate_sprint", "sprint_id": "s2"}),
            ("finish_sprint", "unresolved tasks remain", {"kind": "finish_sprint", "sprint_id": "s1"}),
            ("file_task", "Unsupported task type: nonsense", {"kind": "file_task", "title": "X", "task_type": "nonsense"}),
            ("accept_task", "only tasks in triage", {"kind": "accept_task", "task_id": "todo1"}),
            ("decline_task", "already declined", {"kind": "decline_task", "task_id": declined.id}),
            ("plan_tasks", "accept it before planning", {"kind": "plan_tasks", "task_ids": [filed.id], "sprint_id": "s2"}),
            ("unplan_task", "only a task that has not started", {"kind": "unplan_task", "task_id": "running"}),
            ("edit_task", "Unsupported task type: nonsense", {"kind": "edit_task", "task_id": "todo1", "task_type": "nonsense"}),
            ("block_task", "cannot be blocked from status done", {"kind": "block_task", "task_id": "done1", "reason": "x"}),
            ("unblock_task", "is not blocked", {"kind": "unblock_task", "task_id": "todo1"}),
            ("cancel_task", "already done", {"kind": "cancel_task", "task_id": "done1"}),
            ("send_back", "not waiting for a person", {"kind": "send_back", "task_id": "todo1", "guidance": "x"}),
            ("approve_gate", "not waiting at a gate", {"kind": "approve_gate", "task_id": "running"}),
        ]
        self.assertEqual({kind for kind, _, _ in cases}, set(OPERATION_KINDS))
        for kind, pattern, operation in cases:
            if operation is None:
                continue
            with self.subTest(kind=kind):
                self.assert_refused(pattern, operation)
        # A blocked task that is not at a gate cannot be approved either.
        self.task("parked", "blocked", blocked_reason="Parked.")
        self.assert_refused("not paused on a resumable human-gate step|not paused at a human gate",
                            {"kind": "approve_gate", "task_id": "parked"})


class ConfirmTests(ProposalCase):
    def test_confirm_applies_in_order_as_the_person_with_a_linking_audit_event(self) -> None:
        filed = self.file("Filed")
        self.gate_task("g1")
        proposal = self.propose(
            {"kind": "accept_task", "task_id": filed.id},
            {"kind": "plan_tasks", "task_ids": [filed.id], "new_sprint": {"title": "Sprint 3"}},
            {"kind": "approve_gate", "task_id": "g1"},
            {"kind": "edit_sprint", "sprint_id": "s2", "goal": "Smaller."},
        )

        confirmed = Proposals(self.store, via="dashboard", actor="ada").confirm(proposal.id)

        self.assertEqual(confirmed.state, "confirmed")
        self.assertEqual(confirmed.decided_by, "ada")
        self.assertEqual([step["index"] for step in confirmed.outcome["applied"]], [0, 1, 2, 3])
        self.assertEqual(confirmed.outcome["sentence"], "Applied 4 operations.")
        planned = self.store.get_task(filed.id)
        self.assertEqual(planned.status, "todo")
        self.assertEqual(self.store.get_sprint(planned.sprint_id).title, "Sprint 3")
        self.assertEqual(confirmed.outcome["applied"][1]["sprint_id"], planned.sprint_id)
        self.assertEqual(self.store.get_task("g1").status, "in_progress")
        self.assertEqual(self.store.get_sprint("s2").goal, "Smaller.")

        events = [e for e in self.store.list_events(task_id=filed.id) if e.event_type.startswith("human.")]
        self.assertEqual([e.event_type for e in events], ["human.task_accepted", "human.task_planned"])
        for event in events:
            self.assertEqual(event.payload["proposal_id"], proposal.id)
            self.assertEqual(event.payload["by"], "ada")
            self.assertEqual(event.payload["via"], "dashboard")
        gate_events = {e.event_type: e for e in self.store.list_events(task_id="g1")}
        self.assertEqual(gate_events["human.gate_decided"].payload["proposal_id"], proposal.id)
        self.assertEqual(gate_events["human.gate_decided"].payload["decision"], "approve")

    def test_a_refused_operation_fails_the_proposal_and_applies_nothing(self) -> None:
        filed = self.file("Filed")
        self.task("todo1", "todo", sprint="s2")
        proposal = self.propose(
            {"kind": "accept_task", "task_id": filed.id},
            {"kind": "block_task", "task_id": "todo1", "reason": "Wait."},
            {"kind": "cancel_task", "task_id": "todo1"},
        )
        # The state moves on before anyone confirms.
        Mutations(self.store, via="cli").cancel_task(self.store.get_task("todo1"))
        before = self.snapshot()

        failed = Proposals(self.store, via="cli", actor="ada").confirm(proposal.id)

        self.assertEqual(failed.state, "failed")
        self.assertEqual(failed.decided_by, "ada")
        self.assertEqual(failed.outcome["applied"], [])
        self.assertEqual(failed.outcome["failed"]["index"], 1)
        self.assertEqual(failed.outcome["failed"]["kind"], "block_task")
        self.assertIn("cannot be blocked from status cancelled", failed.outcome["failed"]["reason"])
        self.assertEqual(
            failed.outcome["sentence"],
            "Operation 2 of 3 (block a task) was refused: Task todo1 cannot be blocked from "
            "status cancelled. Nothing was applied.",
        )
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.store.get_task(filed.id).status, "triage")
        self.assertEqual(self.store.get_proposal(proposal.id).state, "failed")

    def test_a_deleted_task_fails_the_proposal(self) -> None:
        self.task("todo1", "todo")
        proposal = self.propose({"kind": "cancel_task", "task_id": "todo1"})
        self.store.delete_task("todo1")
        failed = self.proposals.confirm(proposal.id)
        self.assertEqual(failed.state, "failed")
        self.assertIn("there is no task todo1", failed.outcome["failed"]["reason"])

    def test_decline_records_who_and_changes_nothing(self) -> None:
        self.task("todo1", "todo")
        proposal = self.propose({"kind": "cancel_task", "task_id": "todo1"})
        before = self.snapshot()
        declined = Proposals(self.store, via="cli", actor="grace").decline(proposal.id)
        self.assertEqual((declined.state, declined.decided_by), ("declined", "grace"))
        self.assertIsNotNone(declined.decided_at)
        self.assertEqual(self.snapshot(), before)

    def test_only_a_proposed_proposal_can_be_decided(self) -> None:
        proposal = self.propose({"kind": "create_sprint", "title": "Sprint 3"})
        self.proposals.confirm(proposal.id)
        with self.assertRaisesRegex(ProposalError, "already confirmed by manager-test"):
            self.proposals.confirm(proposal.id)
        with self.assertRaisesRegex(ProposalError, "already confirmed"):
            self.proposals.decline(proposal.id)
        self.assertEqual(len([s for s in self.store.list_sprints("p1") if s.title == "Sprint 3"]), 1)

    def test_a_cancelled_tasks_worktree_is_removed_only_after_the_commit(self) -> None:
        self.task("todo1", "todo", worktree_path=str(Path(self._temp.name) / "wt"))
        removed: list[str] = []
        proposal = self.propose({"kind": "cancel_task", "task_id": "todo1"})
        with mock.patch.object(Mutations, "_remove_worktree", staticmethod(lambda project, path: removed.append(path))):
            # A failing confirm removes nothing.
            task = self.store.get_task("todo1")
            task.status = "done"
            self.store.save_task(task)
            self.assertEqual(self.proposals.confirm(proposal.id).state, "failed")
            self.assertEqual(removed, [])
            task.status = "todo"
            self.store.save_task(task)
            second = self.propose({"kind": "cancel_task", "task_id": "todo1"})
            self.assertEqual(removed, [], "a dry run removed a worktree")
            self.assertEqual(self.proposals.confirm(second.id).state, "confirmed")
        self.assertEqual(removed, [str(Path(self._temp.name) / "wt")])
        self.assertIsNone(self.store.get_task("todo1").worktree_path)


class ProposalApiTests(ProposalCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = create_dashboard_app(self.db_path, auth_token=None)

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async def call():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(call())

    def test_list_filters_by_state_and_pages_newest_first(self) -> None:
        first = self.propose({"kind": "create_sprint", "title": "A"})
        second = self.propose({"kind": "create_sprint", "title": "B"})
        third = self.propose({"kind": "create_sprint", "title": "C"})
        self.proposals.decline(first.id)

        body = self.request("GET", "/api/v1/projects/p1/proposals").json()
        self.assertEqual([p["id"] for p in body["proposals"]], [third.id, second.id, first.id])
        self.assertEqual(body["total"], 3)
        page = self.request("GET", "/api/v1/projects/p1/proposals?limit=1&offset=1").json()
        self.assertEqual([p["id"] for p in page["proposals"]], [second.id])
        open_only = self.request("GET", "/api/v1/projects/p1/proposals?state=proposed").json()
        self.assertEqual(open_only["total"], 2)
        both = self.request("GET", "/api/v1/projects/p1/proposals?state=proposed,declined").json()
        self.assertEqual(both["total"], 3)
        bad = self.request("GET", "/api/v1/projects/p1/proposals?state=maybe")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["code"], "invalid_request")
        self.assertEqual(self.request("GET", "/api/v1/projects/nope/proposals").status_code, 404)

    def test_get_confirm_and_decline(self) -> None:
        filed = self.file("Filed")
        proposal = self.propose({"kind": "accept_task", "task_id": filed.id}, reason="It is ready.")

        shown = self.request("GET", f"/api/v1/proposals/{proposal.id}").json()
        self.assertEqual(shown["state"], "proposed")
        self.assertEqual(shown["reason"], "It is ready.")
        self.assertEqual(shown["names"]["tasks"][filed.id]["title"], "Filed")
        self.assertEqual(self.request("GET", "/api/v1/proposals/nope").status_code, 404)

        confirmed = self.request(
            "POST", f"/api/v1/proposals/{proposal.id}/confirm", json={"requested_by": "ada"}
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["state"], "confirmed")
        self.assertEqual(confirmed.json()["decided_by"], "ada")
        self.assertEqual(self.store.get_task(filed.id).status, "todo")
        event = [e for e in self.store.list_events(task_id=filed.id) if e.event_type == "human.task_accepted"][0]
        self.assertEqual((event.payload["proposal_id"], event.payload["by"], event.payload["via"]),
                         (proposal.id, "ada", "dashboard"))

        again = self.request("POST", f"/api/v1/proposals/{proposal.id}/decline", json={})
        self.assertEqual(again.status_code, 400)
        self.assertIn("already confirmed", again.json()["error"])

        other = self.propose({"kind": "create_sprint", "title": "Later"})
        declined = self.request("POST", f"/api/v1/proposals/{other.id}/decline", json={"requested_by": "grace"})
        self.assertEqual(declined.json()["state"], "declined")
        self.assertEqual(declined.json()["decided_by"], "grace")
        self.assertEqual(self.request("POST", "/api/v1/proposals/nope/confirm", json={}).status_code, 404)

    def test_a_refused_operation_answers_with_the_failed_proposal(self) -> None:
        self.task("todo1", "todo")
        proposal = self.propose({"kind": "cancel_task", "task_id": "todo1"})
        task = self.store.get_task("todo1")
        task.status = "done"
        self.store.save_task(task)

        response = self.request("POST", f"/api/v1/proposals/{proposal.id}/confirm", json={})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state"], "failed")
        self.assertEqual(body["outcome"]["failed"]["index"], 0)
        self.assertIn("Nothing was applied.", body["outcome"]["sentence"])


class ProposalCliTests(ProposalCase):
    def run_cli(self, *argv: str, stdin: str | None = None, env: dict | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        environment = {key: value for key, value in os.environ.items() if not key.startswith("FOREMAN_")}
        environment.update(env or {})
        with mock.patch.dict(os.environ, environment, clear=True), contextlib.redirect_stdout(
            out
        ), contextlib.redirect_stderr(err), mock.patch("sys.stdin", io.StringIO(stdin or "")):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def document(self, *operations, reason="Because.", leaves=None) -> str:
        body = {"reason": reason, "operations": list(operations)}
        if leaves is not None:
            body["leaves"] = leaves
        return json.dumps(body)

    def test_create_from_a_file_and_from_stdin_then_list_show_confirm(self) -> None:
        filed = self.file("Filed")
        path = Path(self._temp.name) / "proposal.json"
        path.write_text(self.document({"kind": "accept_task", "task_id": filed.id}, reason="Ready."))

        code, out, err = self.run_cli("proposal", "create", "p1", "--json", str(path), "--db", self.db_path)
        self.assertEqual(code, 0, err)
        self.assertIn("Nothing changes until a person confirms it.", out)
        self.assertIn(f"1. Accept {filed.task_key} Filed", out)
        self.assertEqual(self.store.get_task(filed.id).status, "triage")

        code, out, err = self.run_cli(
            "proposal", "create", "p1", "--json", "-", "--print-json", "--db", self.db_path,
            stdin=self.document({"kind": "create_sprint", "title": "Sprint 3"}),
        )
        self.assertEqual(code, 0, err)
        second = json.loads(out)
        self.assertEqual(second["state"], "proposed")

        code, out, _ = self.run_cli("proposal", "list", "p1", "--json", "--db", self.db_path)
        listed = json.loads(out)
        self.assertEqual(listed["total"], 2)
        first_id = listed["proposals"][1]["id"]

        code, out, _ = self.run_cli("proposal", "show", first_id, "--db", self.db_path)
        self.assertEqual(code, 0)
        self.assertIn("Reason: Ready.", out)

        code, out, err = self.run_cli("proposal", "confirm", first_id, "--db", self.db_path)
        self.assertEqual(code, 0, err)
        self.assertIn("Outcome: Applied 1 operation.", out)
        self.assertEqual(self.store.get_task(filed.id).status, "todo")
        accepted = [e for e in self.store.list_events(task_id=filed.id) if e.event_type == "human.task_accepted"][0]
        self.assertEqual(accepted.payload["proposal_id"], first_id)
        self.assertEqual(accepted.payload["via"], "cli")
        self.assertTrue(accepted.payload["by"])

        code, out, _ = self.run_cli("proposal", "decline", second["id"], "--json", "--db", self.db_path)
        self.assertEqual(json.loads(out)["state"], "declined")
        self.assertTrue(json.loads(out)["decided_by"])

    def test_a_refused_create_says_why_and_stores_nothing(self) -> None:
        self.task("done1", "done")
        code, out, err = self.run_cli(
            "proposal", "create", "p1", "--json", "-", "--db", self.db_path,
            stdin=self.document(
                {"kind": "create_sprint", "title": "Sprint 3"},
                {"kind": "cancel_task", "task_id": "done1"},
            ),
        )
        self.assertEqual(code, 1)
        self.assertIn("Refused, nothing stored. Operation 2 (cancel a task): Task done1 is already done", err)
        self.assertEqual(self.count_proposals(), 0)
        self.assertNotIn("Sprint 3", [s.title for s in self.store.list_sprints("p1")])

        code, _, err = self.run_cli("proposal", "create", "p1", "--json", "-", "--db", self.db_path, stdin="{nope")
        self.assertEqual(code, 1)
        self.assertIn("Could not read the proposal", err)

    def test_a_failed_confirm_exits_non_zero_and_says_so(self) -> None:
        self.task("todo1", "todo")
        proposal = self.propose({"kind": "cancel_task", "task_id": "todo1"})
        self.store.delete_task("todo1")
        code, out, _ = self.run_cli("proposal", "confirm", proposal.id, "--db", self.db_path)
        self.assertEqual(code, 1)
        self.assertIn("Outcome: Operation 1 of 1 (cancel a task) was refused", out)


class ManagerSessionTests(ProposalCase):
    """Inside a manager session the CLI reads and proposes, and refuses every change."""

    SESSION = {"FOREMAN_MANAGER_SESSION": "p1", "FOREMAN_MANAGER_TURN": "turn-7"}

    run_cli = ProposalCliTests.run_cli
    document = ProposalCliTests.document

    def test_mutating_commands_are_refused_with_a_sentence_saying_to_propose(self) -> None:
        filed = self.file("Filed")
        self.task("todo1", "todo")
        before = self.snapshot()
        commands = [
            ("sprint", "add", "p1", "--title", "X", "--goal", "Y"),
            ("sprint", "activate", "s2"),
            ("backlog", "accept", filed.id),
            ("backlog", "add", "p1", "--title", "X"),
            ("task", "cancel", "todo1"),
            ("task", "block", "todo1", "--reason", "x"),
            ("approve", "todo1"),
            ("engine", "pause", "p1"),
            ("run", "p1"),
            ("proposal", "confirm", "prop-x"),
            ("proposal", "decline", "prop-x"),
        ]
        for argv in commands:
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(*argv, "--db", self.db_path, env=self.SESSION)
                self.assertEqual(code, 1)
                self.assertIn("refused. Foreman's manager cannot change project state itself.", err)
                self.assertIn("foreman proposal create <project> --json <file or ->", err)
        self.assertEqual(self.snapshot(), before)

    def test_read_commands_still_work(self) -> None:
        self.task("todo1", "todo")
        for argv in (
            ("board", "p1"),
            ("task", "show", "todo1"),
            ("sprint", "list", "p1"),
            ("backlog", "list", "p1"),
            ("proposal", "list", "p1"),
        ):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(*argv, "--db", self.db_path, env=self.SESSION)
                self.assertEqual(code, 0, err)

    def test_the_database_comes_from_the_session(self) -> None:
        code, out, err = self.run_cli(
            "sprint", "list", "p1", env={**self.SESSION, "FOREMAN_DB": self.db_path}
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Sprint 2", out)

    def test_a_proposal_from_the_session_is_the_managers_and_names_its_turn(self) -> None:
        code, out, err = self.run_cli(
            "proposal", "create", "p1", "--json", "-", "--print-json", "--db", self.db_path,
            env=self.SESSION, stdin=self.document({"kind": "activate_sprint", "sprint_id": "s2"}, reason="x"),
        )
        # s1 is active, so activating s2 is refused; propose finishing nothing instead.
        self.assertEqual(code, 1)
        self.assertIn("already active", err)
        code, out, err = self.run_cli(
            "proposal", "create", "p1", "--json", "-", "--print-json", "--db", self.db_path,
            env=self.SESSION, stdin=self.document({"kind": "edit_sprint", "sprint_id": "s2", "title": "Two"}),
        )
        self.assertEqual(code, 0, err)
        created = json.loads(out)
        self.assertEqual((created["proposed_by"], created["turn_id"]), (MANAGER, "turn-7"))

    def test_a_session_proposes_only_for_its_own_project(self) -> None:
        code, _, err = self.run_cli(
            "proposal", "create", "p2", "--json", "-", "--db", self.db_path,
            env=self.SESSION, stdin=self.document({"kind": "create_sprint", "title": "X"}),
        )
        self.assertEqual(code, 1)
        self.assertIn("belongs to project p1", err)

    def test_every_allowed_command_exists_and_none_of_them_writes_project_state(self) -> None:
        from foreman.cli import build_parser

        paths = set()

        def collect(parser, prefix=()):
            for action in parser._actions:
                if hasattr(action, "choices") and isinstance(action.choices, dict):
                    for name, sub in action.choices.items():
                        path = prefix + (name,)
                        defaults = sub._defaults
                        if "command_path" in defaults:
                            paths.add(defaults["command_path"])
                        collect(sub, path)

        collect(build_parser())
        self.assertLessEqual(MANAGER_SESSION_COMMANDS, paths)
        for mutating in ("task add", "task override", "backlog plan", "config", "token create", "worktree prune"):
            self.assertIn(mutating, paths)
            self.assertNotIn(mutating, MANAGER_SESSION_COMMANDS)


if __name__ == "__main__":
    unittest.main()
