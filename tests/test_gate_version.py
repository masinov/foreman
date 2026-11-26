"""A gate decision records the version it decided on, and refuses one that changed."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path

import httpx

from foreman.api.app import create_dashboard_app
from foreman.domain.gate_version import plan_fingerprint
from foreman.domain.models import Project, Run, Sprint, Task
from foreman.manager.proposals import Proposals
from foreman.store import ForemanStore, _SCHEMA_MIGRATIONS_DDL
from foreman.store.migrations import MIGRATIONS

from plan_workflow import install_plan_workflow
from test_cli import cli_argv, cli_env


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    return done.stdout.strip()


class GateVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        git(self.repo, "init")
        git(self.repo, "symbolic-ref", "HEAD", "refs/heads/main")
        (self.repo / "a.txt").write_text("a\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "init")
        git(self.repo, "branch", "feat/x")
        self.db = root / "foreman.db"
        self.store = ForemanStore(self.db)
        self.store.initialize()
        self.addCleanup(self.store.close)

    def seed(self, *, plan: bool) -> Task:
        project = Project(
            id="p", name="P", repo_path=str(self.repo),
            workflow_id="development_with_architect" if plan else "development",
            default_branch="main",
        )
        self.store.save_project(project)
        if plan:
            install_plan_workflow(self.store, project.id)
        self.store.save_sprint(Sprint(id="s", project_id="p", title="S", status="active"))
        task = Task(
            id="t", sprint_id="s", project_id="p", title="T", status="blocked",
            task_type="feature", branch_name="feat/x",
            description="Do it", acceptance_criteria="- it works",
            workflow_current_step="human_approval" if plan else "merge_approval",
            blocked_reason="Awaiting human approval",
        )
        self.store.save_task(task)
        return task

    def move_branch(self) -> tuple[str, str]:
        before = git(self.repo, "rev-parse", "feat/x")
        git(self.repo, "checkout", "-q", "feat/x")
        (self.repo / "b.txt").write_text("b\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "more")
        after = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "checkout", "-q", "main")
        return before, after

    def api(self, method: str, url: str, **kwargs) -> httpx.Response:
        async def send():
            transport = httpx.ASGITransport(app=create_dashboard_app(str(self.db)))
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
                return await c.request(method, url, **kwargs)
        return asyncio.run(send())

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cli_argv(*args, "--db", str(self.db)), env=cli_env(),
                              capture_output=True, text=True, check=False)

    def decision(self):
        return (
            self.store.get_human_gate_decision("t", "merge_approval")
            or self.store.get_human_gate_decision("t", "human_approval")
        )

    # -- merge approval

    def test_merge_approval_records_both_heads_and_the_activity_names_the_commit(self) -> None:
        self.seed(plan=False)
        head = git(self.repo, "rev-parse", "feat/x")
        main = git(self.repo, "rev-parse", "main")
        shown = self.api("GET", "/api/tasks/t").json()["gate_version"]
        self.assertEqual((shown["kind"], shown["branch_sha"], shown["base_sha"]), ("merge_approval", head, main))
        response = self.api("POST", "/api/tasks/t/approve", json={"version": head})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["version_named"])
        recorded = self.decision()
        self.assertEqual((recorded.branch_sha, recorded.base_sha, recorded.version_named), (head, main, True))
        runs = self.api("GET", "/api/tasks/t").json()["runs"]
        gate = [r for r in runs if r["workflow_step"] == "merge_approval"][0]
        self.assertEqual(gate["commit_sha"], head)

    def test_merge_approval_of_a_moved_branch_is_refused_with_the_new_version(self) -> None:
        self.seed(plan=False)
        seen = git(self.repo, "rev-parse", "feat/x")
        _, after = self.move_branch()
        response = self.api("POST", "/api/tasks/t/approve", json={"version": seen})
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["code"], "version_changed")
        self.assertIn(seen[:7], body["error"] if "error" in body else str(body))
        self.assertIn(after[:7], str(body))
        self.assertEqual(body["current"]["branch_sha"], after)
        self.assertEqual(self.store.get_task("t").status, "blocked")
        self.assertIsNone(self.decision())

    def test_api_approval_without_a_version_is_recorded_against_the_current_one(self) -> None:
        self.seed(plan=False)
        head = git(self.repo, "rev-parse", "feat/x")
        response = self.api("POST", "/api/tasks/t/approve")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["version_named"])
        self.assertEqual(response.json()["version"]["branch_sha"], head)
        self.assertEqual(self.decision().branch_sha, head)
        self.assertFalse(self.decision().version_named)

    def test_cli_refuses_a_moved_branch_and_says_what_it_recorded_otherwise(self) -> None:
        self.seed(plan=False)
        seen = git(self.repo, "rev-parse", "feat/x")
        _, after = self.move_branch()
        refused = self.cli("approve", "t", "--version", seen)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("moved", refused.stderr)
        self.assertIn(after[:7], refused.stderr)
        self.assertEqual(self.store.get_task("t").status, "blocked")

        approved = self.cli("approve", "t")
        self.assertEqual(approved.returncode, 0, approved.stderr)
        self.assertIn(f"Version: recorded against branch {after[:7]}", approved.stdout)
        self.assertIn("no version named", approved.stdout)

    def test_cli_approval_naming_the_current_version_says_so_and_history_shows_the_commit(self) -> None:
        self.seed(plan=False)
        head = git(self.repo, "rev-parse", "feat/x")
        approved = self.cli("approve", "t", "--version", head[:10])
        self.assertEqual(approved.returncode, 0, approved.stderr)
        self.assertIn("the version you named", approved.stdout)
        history = self.cli("history", "t")
        self.assertEqual(history.returncode, 0, history.stderr)
        self.assertIn(f"at={head[:7]}", history.stdout)

    def test_a_send_back_does_not_need_the_version_to_be_current(self) -> None:
        self.seed(plan=False)
        response = self.api("POST", "/api/tasks/t/deny", json={"note": "no"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNotNone(self.decision().branch_sha)

    # -- plan approval

    def test_plan_approval_records_the_fingerprint_and_refuses_an_edited_plan(self) -> None:
        task = self.seed(plan=True)
        fingerprint = plan_fingerprint("Do it", "- it works")
        shown = self.api("GET", "/api/tasks/t").json()["gate_version"]
        self.assertEqual((shown["kind"], shown["fingerprint"]), ("plan_approval", fingerprint))
        task.description = "Do something else"
        self.store.save_task(task)
        refused = self.api("POST", "/api/tasks/t/approve", json={"version": fingerprint})
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["code"], "version_changed")
        self.assertIsNone(self.decision())

        current = plan_fingerprint("Do something else", "- it works")
        approved = self.api("POST", "/api/tasks/t/approve", json={"version": current})
        self.assertEqual(approved.status_code, 200, approved.text)
        recorded = self.decision()
        self.assertEqual((recorded.plan_fingerprint, recorded.version_named), (current, True))
        self.assertIsNone(recorded.branch_sha)

    def add_run(self, run_id: str, *, step: str, role: str, backend: str) -> Run:
        return self.store.save_run(Run(
            id=run_id, task_id="t", project_id="p", role_id=role, workflow_step=step,
            agent_backend=backend, status="completed", outcome="done",
        ))

    def test_the_plan_is_the_last_agent_run_of_the_step_before_the_gate(self) -> None:
        self.seed(plan=True)
        self.add_run("run-plan-1", step="plan", role="architect", backend="claude")
        # Neither a person's decision, nor an engine record, nor a later step writes a plan.
        self.add_run("run-gate", step="human_approval", role="_builtin:human_gate", backend="human")
        self.add_run("run-record", step="human_approval", role="_builtin:orchestrator", backend="orchestrator")
        shown = self.api("GET", "/api/tasks/t").json()["gate_version"]
        self.assertEqual(shown["plan_run_id"], "run-plan-1")
        self.assertEqual(shown["fingerprint"], plan_fingerprint("Do it", "- it works", "run-plan-1"))
        self.assertEqual(shown["token"], shown["fingerprint"])

        # The plan redone, with the same words: another version.
        self.add_run("run-plan-2", step="plan", role="architect", backend="claude")
        refused = self.api("POST", "/api/tasks/t/approve", json={"version": shown["token"]})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()["current"]["plan_run_id"], "run-plan-2")
        self.assertIsNone(self.decision())
        approved = self.api("POST", "/api/tasks/t/approve", json={"version": refused.json()["current"]["token"]})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(self.decision().plan_run_id, "run-plan-2")

    # -- requests that name no version of the gate

    def test_a_malformed_version_is_a_bad_request_with_the_reason(self) -> None:
        self.seed(plan=False)
        for seen, reason in (("abc12", "too short"), ("zzzzzzzz", "not one"), ("abc 1234", "not one")):
            with self.subTest(seen=seen):
                response = self.api("POST", "/api/tasks/t/approve", json={"version": seen})
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn(reason, response.json()["error"])
                self.assertNotIn("None", response.json()["error"])
        self.assertIsNone(self.decision())
        self.assertEqual(self.store.get_task("t").status, "blocked")

    def test_a_version_at_a_gate_with_nothing_to_name_is_a_bad_request(self) -> None:
        task = self.seed(plan=False)
        task.branch_name = "feat/gone"
        self.store.save_task(task)
        response = self.api("POST", "/api/tasks/t/approve", json={"version": "abcdef1"})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("no version to name", response.json()["error"])
        self.assertNotIn("now at None", response.text)

    # -- what the answer and the lists say

    def test_the_answer_says_the_version_it_was_recorded_against(self) -> None:
        self.seed(plan=False)
        head = git(self.repo, "rev-parse", "feat/x")
        unnamed = self.api("POST", "/api/tasks/t/approve").json()
        self.assertIn(f"Approved P-1 (recorded at {head[:7]}). It waits at Merge", unnamed["message"])

    def test_the_answer_to_a_named_version_says_it(self) -> None:
        self.seed(plan=False)
        head = git(self.repo, "rev-parse", "feat/x")
        named = self.api("POST", "/api/tasks/t/approve", json={"version": head}).json()
        self.assertIn(f"Approved P-1 at {head[:7]}. It waits at Merge", named["message"])

    def test_the_lists_that_offer_approve_carry_the_version(self) -> None:
        self.seed(plan=False)
        head = git(self.repo, "rev-parse", "feat/x")
        rows = self.api("GET", "/api/sprints/s/tasks").json()["tasks"]
        self.assertEqual(rows[0]["gate_version"]["branch_sha"], head)
        items = self.api("GET", "/api/needs-you").json()["items"]
        merge = [item for item in items if item["kind"] == "approve_merge"]
        self.assertEqual(merge[0]["gate_version"]["token"], head)

    def test_a_gate_run_says_the_version_and_whether_it_was_named(self) -> None:
        self.seed(plan=False)
        head = git(self.repo, "rev-parse", "feat/x")
        self.api("POST", "/api/tasks/t/approve", json={"version": head[:9]})
        runs = self.api("GET", "/api/tasks/t/runs").json()["runs"]
        gate = [r for r in runs if r["step"] == "merge_approval"][0]
        self.assertEqual((gate["gate_version"]["branch_sha"], gate["gate_version"]["named"]), (head, True))

    # -- the manager's proposal

    def test_a_proposed_approval_is_of_the_version_when_it_was_proposed(self) -> None:
        self.seed(plan=False)
        project = self.store.get_project("p")
        proposals = Proposals(self.store, via="cli", actor="ada")
        seen = git(self.repo, "rev-parse", "feat/x")
        stale = proposals.create(
            project, reason="Ready.", operations=[{"kind": "approve_gate", "task_id": "t"}],
            proposed_by="manager",
        )
        self.assertEqual(stale.operations[0]["version"], seen)
        _, after = self.move_branch()
        failed = proposals.confirm(stale.id)
        self.assertEqual(failed.state, "failed")
        self.assertIn("The branch moved", failed.outcome["failed"]["reason"])
        self.assertIn(after[:7], failed.outcome["failed"]["reason"])
        self.assertIsNone(self.decision())

        fresh = proposals.create(
            project, reason="Ready now.", operations=[{"kind": "approve_gate", "task_id": "t"}],
            proposed_by="manager",
        )
        self.assertEqual(proposals.confirm(fresh.id).state, "confirmed")
        self.assertEqual((self.decision().branch_sha, self.decision().version_named), (after, True))

    # -- older decisions

    def test_the_migration_leaves_older_decisions_open(self) -> None:
        # A database as it was before the versions were kept: every migration
        # but the one that adds them, and a decision written then.
        db = Path(self.temp.name) / "old.db"
        old = ForemanStore(db)
        self.addCleanup(old.close)
        with old._connection:
            old._connection.executescript(_SCHEMA_MIGRATIONS_DDL)
        before = [m for m in MIGRATIONS if m[0] < 35]
        old.migrate(before)
        self.assertEqual(old.schema_version(), 34)
        columns = {row[1] for row in old._connection.execute("PRAGMA table_info(human_gate_decisions)")}
        self.assertNotIn("branch_sha", columns)
        with old._connection:
            old._connection.execute("PRAGMA foreign_keys = OFF")
            old._connection.execute(
                "INSERT INTO human_gate_decisions (id, task_id, project_id, workflow_step,"
                " decision, decided_at) VALUES ('old','t','p','merge_approval','approve','2026-01-01T00:00:00Z')"
            )

        old._connection.execute("PRAGMA foreign_keys = ON")
        old.initialize()

        self.assertGreaterEqual(old.schema_version(), 35)
        decision = old.get_human_gate_decision("t", "merge_approval")
        self.assertEqual(decision.id, "old")
        self.assertEqual(
            (decision.branch_sha, decision.base_sha, decision.plan_fingerprint,
             decision.plan_run_id, decision.version_named),
            (None, None, None, None, False),
        )

if __name__ == "__main__":
    unittest.main()
