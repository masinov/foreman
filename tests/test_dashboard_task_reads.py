"""A task's changes, diff, checks and runs (sprint 58 slice 7)."""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import tempfile
import unittest

import httpx

from foreman.api.app import create_dashboard_app
from foreman.services.task_models import DIFF_CAP_CHARS, OUTPUT_CAP_CHARS
from foreman.domain.models import CompletionEvidence, Event, Project, Run, Sprint, Task
from foreman.store import ForemanStore


class TaskReadsCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.repo = Path(self._temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("checkout", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")
        self.write("keep.txt", "keep\n")
        self.write("old.txt", "one\ntwo\nthree\nfour\nfive\n")
        self.write("gone.txt", "bye\n")
        self.commit("chore: initial")

        self.db_path = str(Path(self._temp.name) / "foreman.db")
        self.store = ForemanStore(self.db_path)
        self.store.initialize()
        self.addCleanup(self.store.close)
        self.store.save_project(
            Project(id="p", name="P", repo_path=str(self.repo), workflow_id="development")
        )
        self.store.save_sprint(Sprint(id="s", project_id="p", title="S", status="active"))
        self.app = create_dashboard_app(self.db_path, auth_token=None)

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.repo, capture_output=True, text=True, check=True
        ).stdout.strip()

    def write(self, name: str, text: str) -> None:
        (self.repo / name).write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def branch_with_changes(self, name: str = "feat/x") -> None:
        self.git("checkout", "-q", "-b", name)
        self.write("new.txt", "a\nb\n")
        self.write("keep.txt", "keep\nmore\n")
        (self.repo / "gone.txt").unlink()
        self.git("mv", "old.txt", "renamed.txt")
        self.commit("feat: change things")
        self.git("checkout", "-q", "main")

    def task(self, tid: str = "t", **kw) -> Task:
        return self.store.save_task(
            Task(id=tid, sprint_id="s", project_id="p", title=f"Task {tid}", status="todo", **kw)
        )

    def get(self, path: str) -> httpx.Response:
        async def call():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
                return await c.get(path)

        return asyncio.run(call())

    # ── changes ──────────────────────────────────────────────────────────

    def test_changes_lists_files_totals_and_commits(self) -> None:
        self.branch_with_changes()
        self.task(branch_name="feat/x")
        body = self.get("/api/v1/tasks/t/changes").json()
        files = {f["path"]: f for f in body["files"]}
        self.assertEqual(files["new.txt"]["status"], "added")
        self.assertEqual((files["new.txt"]["added"], files["new.txt"]["deleted"]), (2, 0))
        self.assertEqual(files["keep.txt"]["status"], "modified")
        self.assertEqual(files["gone.txt"]["status"], "deleted")
        self.assertEqual(files["gone.txt"]["deleted"], 1)
        self.assertEqual(files["renamed.txt"]["status"], "renamed")
        self.assertEqual(files["renamed.txt"]["old_path"], "old.txt")
        self.assertEqual(body["totals"], {"files": 4, "added": 3, "deleted": 1})
        self.assertEqual(body["base"]["sha"], self.git("rev-parse", "main"))
        self.assertEqual(body["head"]["sha"], self.git("rev-parse", "feat/x"))
        self.assertIsNone(body["empty_reason"])

    def merge(self, name: str = "feat/x") -> str:
        self.git("merge", "-q", "--no-ff", name, "-m", f"Merge branch '{name}' into main")
        merged = self.git("rev-parse", "main")
        self.write("later.txt", "after\n")
        self.commit("chore: main moves on")
        return merged

    def test_a_merged_task_shows_what_it_landed(self) -> None:
        self.branch_with_changes()
        self.task(branch_name="feat/x")
        before = self.git("rev-parse", "main")
        merged = self.merge()

        body = self.get("/api/v1/tasks/t/changes").json()

        self.assertEqual(body["totals"], {"files": 4, "added": 3, "deleted": 1})
        self.assertEqual(body["merged_as"], merged)
        self.assertEqual((body["base"]["sha"], body["head"]["sha"]), (before, merged))
        self.assertNotIn("later.txt", [f["path"] for f in body["files"]])
        diff = self.get("/api/v1/tasks/t/changes/diff?path=new.txt").json()
        self.assertIn("+a", diff["diff"])

    def test_a_merged_task_whose_branch_is_gone_still_shows_it(self) -> None:
        from foreman.domain.models import CompletionEvidence

        self.branch_with_changes()
        head = self.git("rev-parse", "feat/x")
        task = self.task(branch_name="feat/x")
        merged = self.merge()
        self.git("branch", "-q", "-D", "feat/x")
        task.completion_evidence = CompletionEvidence(task_id="t", task_title="Task t", acceptance_criteria="", head_sha=head)
        self.store.save_task(task)

        body = self.get("/api/v1/tasks/t/changes").json()

        self.assertEqual((body["totals"]["files"], body["merged_as"]), (4, merged))

    def test_a_merged_task_is_not_called_behind(self) -> None:
        self.branch_with_changes()
        self.task(branch_name="feat/x")
        merged = self.merge()

        facts = self.get("/api/v1/tasks/t/checks").json()["facts"]

        self.assertEqual((facts["branch"]["state"], facts["branch"]["merged_as"]), ("merged", merged))
        self.assertIsNone(facts["branch"]["behind"])
        self.assertEqual(facts["size"]["files"], 4)

    def test_task_without_branch_says_why(self) -> None:
        self.task()
        body = self.get("/api/v1/tasks/t/changes").json()
        self.assertEqual(body["files"], [])
        self.assertEqual(body["totals"], {"files": 0, "added": 0, "deleted": 0})
        self.assertIn("no branch", body["empty_reason"])
        self.assertIsNone(body["head"])

    def test_branch_missing_from_repository_says_why(self) -> None:
        self.task(branch_name="feat/gone")
        body = self.get("/api/v1/tasks/t/changes").json()
        self.assertEqual(body["files"], [])
        self.assertIn("no longer exists", body["empty_reason"])

    def test_unknown_task_is_404_envelope(self) -> None:
        response = self.get("/api/v1/tasks/nope/changes")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")

    # ── diff ─────────────────────────────────────────────────────────────

    def test_diff_of_changed_file(self) -> None:
        self.branch_with_changes()
        self.task(branch_name="feat/x")
        body = self.get("/api/v1/tasks/t/changes/diff?path=keep.txt").json()
        self.assertIn("+more", body["diff"])
        self.assertFalse(body["truncated"])
        self.assertEqual(body["cap_chars"], DIFF_CAP_CHARS)
        renamed = self.get("/api/v1/tasks/t/changes/diff?path=renamed.txt").json()
        self.assertIn("rename from old.txt", renamed["diff"])

    def test_diff_of_unchanged_path_is_400(self) -> None:
        self.branch_with_changes()
        self.task(branch_name="feat/x")
        response = self.get("/api/v1/tasks/t/changes/diff?path=README.md")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_request")

    def test_diff_rejects_traversal_globs_and_options(self) -> None:
        self.branch_with_changes()
        self.task(branch_name="feat/x")
        for bad in ("../../etc/passwd", "/etc/passwd", "*", "--output=/tmp/x", "keep.txt/../old.txt", ":(top)keep.txt"):
            query = httpx.QueryParams({"path": bad})
            response = self.get(f"/api/v1/tasks/t/changes/diff?{query}")
            self.assertEqual(response.status_code, 400, bad)
            self.assertEqual(response.json()["code"], "invalid_request", bad)

    def test_diff_requires_path(self) -> None:
        self.task()
        self.assertEqual(self.get("/api/v1/tasks/t/changes/diff").status_code, 400)

    def test_diff_is_truncated_at_the_cap(self) -> None:
        self.git("checkout", "-q", "-b", "feat/big")
        self.write("big.txt", "x" * 100 + "\n")
        self.write("big.txt", ("y" * 99 + "\n") * (DIFF_CAP_CHARS // 100 + 500))
        self.commit("feat: big")
        self.git("checkout", "-q", "main")
        self.task(branch_name="feat/big")
        body = self.get("/api/v1/tasks/t/changes/diff?path=big.txt").json()
        self.assertTrue(body["truncated"])
        self.assertEqual(len(body["diff"]), DIFF_CAP_CHARS)
        self.assertGreater(body["total_chars"], DIFF_CAP_CHARS)

    # ── checks ───────────────────────────────────────────────────────────

    def test_checks_with_full_evidence(self) -> None:
        self.branch_with_changes()
        head = self.git("rev-parse", "feat/x")
        evidence = CompletionEvidence(
            task_id="t", task_title="T", acceptance_criteria="a\nb",
            tests_status="passed", tested_sha=head, head_sha=head,
            review_outcome="approve", reviewed_sha=head, proof_status="passed",
            criteria_checklist=(
                {"criterion": "a", "status": "passed", "evidence": "see new.txt"},
                {"criterion": "b", "status": "partial", "evidence": ""},
            ),
        )
        self.task(branch_name="feat/x", acceptance_criteria="a\nb", completion_evidence=evidence)
        self.store.save_run(Run(
            id="r-test", task_id="t", project_id="p", role_id="_builtin:test", workflow_step="test",
            agent_backend="builtin", status="completed", created_at="2026-01-01T00:00:01Z"))
        self.store.save_event(Event(
            id="e1", run_id="r-test", task_id="t", project_id="p", event_type="engine.test_run",
            timestamp="2026-01-01T00:00:02Z",
            payload={"command": "pytest -q", "exit_code": 0, "duration_seconds": 3.2,
                     "head_sha": head, "output_tail": "collected\n12 passed in 3.1s\n",
                     "report": {"tests": 12, "passed": 11, "failed": 0, "skipped": 1, "files": 1}}))
        self.store.save_run(Run(
            id="r-rev", task_id="t", project_id="p", role_id="reviewer", workflow_step="review",
            agent_backend="claude_code", status="completed", model="opus", duration_ms=45_000,
            outcome="approve", outcome_detail="Looks right.", created_at="2026-01-01T00:00:03Z"))
        self.store.save_event(Event(
            id="e2", run_id="r-rev", task_id="t", project_id="p", event_type="engine.review_recorded",
            timestamp="2026-01-01T00:00:04Z",
            payload={"role": "reviewer", "review_kind": "code", "outcome": "approve", "head_sha": head}))

        body = self.get("/api/v1/tasks/t/checks").json()
        tests = body["facts"]["tests"]
        self.assertEqual(tests["status"], "passed")
        self.assertEqual(tests["command"], "pytest -q")
        self.assertEqual(tests["result_line"], "12 passed in 3.1s")
        self.assertEqual(tests["counts"], {"tests": 12, "passed": 11, "failed": 0, "skipped": 1, "failed_tests": []})
        self.assertEqual(tests["duration_seconds"], 3.2)
        self.assertEqual(tests["commit"], head)
        self.assertEqual(body["facts"]["branch"]["state"], "current")
        self.assertEqual(body["facts"]["branch"]["ahead"], 1)
        self.assertEqual(body["facts"]["size"], {"files": 4, "added": 3, "deleted": 1})
        review = body["claims"]["reviews"][0]
        self.assertEqual(
            (review["kind"], review["decision"], review["model"], review["duration_seconds"]),
            ("code", "approve", "opus", 45.0),
        )
        self.assertEqual(review["summary"], "Looks right.")
        self.assertTrue(review["current"])
        self.assertNotIn("judged_by", body["claims"])
        self.assertEqual([c["status"] for c in body["claims"]["criteria"]], ["passed", "partial"])
        self.assertEqual(body["evidence_files"], [])
        self.assertEqual(body["proof_status"], "passed")

    def test_checks_for_task_with_no_evidence(self) -> None:
        self.task(acceptance_criteria="first\nsecond")
        body = self.get("/api/v1/tasks/t/checks").json()
        self.assertEqual(body["facts"]["tests"]["status"], "not_run")
        self.assertEqual(body["facts"]["branch"]["state"], "no_branch")
        self.assertEqual(body["facts"]["size"], {"files": 0, "added": 0, "deleted": 0})
        self.assertEqual(body["claims"]["reviews"], [])
        self.assertEqual(
            [(c["criterion"], c["status"]) for c in body["claims"]["criteria"]],
            [("first", "unverified"), ("second", "unverified")],
        )
        self.assertIsNone(body["proof_status"])
        self.assertEqual(body["evidence_files"], [])

    def test_tests_on_an_older_commit_are_stale(self) -> None:
        self.branch_with_changes()
        self.task(branch_name="feat/x")
        self.store.save_run(Run(
            id="r", task_id="t", project_id="p", role_id="_builtin:test", workflow_step="test",
            agent_backend="builtin", created_at="2026-01-01T00:00:01Z"))
        self.store.save_event(Event(
            id="e", run_id="r", task_id="t", project_id="p", event_type="engine.test_run",
            timestamp="2026-01-01T00:00:02Z", payload={"command": "x", "exit_code": 0, "head_sha": "0" * 40}))
        self.assertEqual(self.get("/api/v1/tasks/t/checks").json()["facts"]["tests"]["status"], "stale")

    # ── runs ─────────────────────────────────────────────────────────────

    def add_runs(self, count: int) -> None:
        for n in range(count):
            self.store.save_run(Run(
                id=f"r{n}", task_id="t", project_id="p", role_id="developer", workflow_step="develop",
                agent_backend="claude_code", status="completed", outcome="success", model="m",
                cost_usd=0.5, token_count=10, duration_ms=1000,
                started_at=f"2026-01-01T00:00:0{n}Z", completed_at=f"2026-01-01T00:00:0{n}Z",
                created_at=f"2026-01-01T00:00:0{n}Z"))

    def test_runs_are_newest_first_and_paged(self) -> None:
        self.task()
        self.add_runs(5)
        page = self.get("/api/v1/tasks/t/runs?limit=2&offset=1").json()
        self.assertEqual([r["id"] for r in page["runs"]], ["r3", "r2"])
        self.assertEqual((page["total"], page["limit"], page["offset"]), (5, 2, 1))
        first = page["runs"][0]
        self.assertEqual((first["step"], first["role_id"], first["model"]), ("develop", "developer", "m"))
        self.assertEqual((first["cost_usd"], first["tokens"], first["duration_ms"]), (0.5, 10, 1000))
        self.assertIsNone(first["commit_sha"])
        self.assertEqual(self.get("/api/v1/tasks/t/runs?limit=0").status_code, 400)
        self.assertEqual(self.get("/api/v1/tasks/nope/runs").status_code, 404)

    def test_runs_name_the_commit_they_left(self) -> None:
        self.task()
        self.add_runs(2)
        run = self.store.get_run("r1")
        run.commit_sha = "b232eb1" + "0" * 33
        self.store.save_run(run)
        runs = {r["id"]: r for r in self.get("/api/v1/tasks/t/runs").json()["runs"]}
        self.assertEqual(runs["r1"]["commit_sha"], "b232eb1" + "0" * 33)
        self.assertIsNone(runs["r0"]["commit_sha"])
        detail = {r["id"]: r for r in self.get("/api/v1/tasks/t").json()["runs"]}
        self.assertEqual(detail["r1"]["commit_sha"], "b232eb1" + "0" * 33)
        self.assertIsNone(detail["r0"]["commit_sha"])

    def test_runs_are_the_tasks_own_steps_with_their_attempt_and_commit(self) -> None:
        self.task()

        def run(rid: str, minute: int, **kw) -> None:
            fields = dict(
                id=rid, task_id="t", project_id="p", role_id="developer", workflow_step="develop",
                agent_backend="claude_code", status="completed", outcome="done", model="m",
                created_at=f"2026-01-01T00:{minute:02d}:00Z", started_at=f"2026-01-01T00:{minute:02d}:00Z",
            )
            fields.update(kw)
            self.store.save_run(Run(**fields))

        engine = dict(role_id="_builtin:orchestrator", agent_backend="orchestrator", model=None, outcome="success")
        run("d1", 1, commit_sha="a" * 40)
        run("stop", 2, outcome_detail="Shut down during task 't': the agent process group was terminated.", **engine)
        run("d2", 3, commit_sha="b" * 40)
        run("t1", 4, role_id="_builtin:run_tests", workflow_step="test", agent_backend="builtin", model=None, outcome="success")
        run("m1", 5, role_id="_builtin:merge", workflow_step="merge", agent_backend="builtin", model=None, outcome="success")
        run("done", 6, role_id="_builtin:mark_done", workflow_step="done", agent_backend="builtin", model=None, outcome="success")
        run("head", 8, outcome_detail="Default branch 'main' HEAD changed from 'x' to 'y'.", **{**engine, "outcome": "blocked"})
        self.store.save_event(Event(id="e-test", run_id="t1", task_id="t", project_id="p", event_type="engine.test_run",
                                    timestamp="2026-01-01T00:04:30Z", payload={
                                        "head_sha": "b" * 40, "exit_code": 0,
                                        "report": {"tests": 186, "passed": 183, "failed": 3, "skipped": 0, "files": 2,
                                                   "failed_tests": [{"suite": "tests.test_a.ATests", "name": "test_x"}]}}))
        self.store.save_event(Event(id="e-merge", run_id="m1", task_id="t", project_id="p", event_type="engine.merge",
                                    timestamp="2026-01-01T00:05:30Z", payload={"sha": "c" * 40, "target": "main"}))

        page = self.get("/api/v1/tasks/t/runs").json()
        # Left out: closing the task after its merge. Every record the engine
        # kept on the task is listed, whether or not it names it (ADR-0037).
        self.assertEqual([r["id"] for r in page["runs"]], ["head", "m1", "t1", "d2", "stop", "d1"])
        self.assertEqual(page["total"], 6)
        runs = {r["id"]: r for r in page["runs"]}
        # The engine's record is not an attempt at the step it was kept under.
        self.assertEqual({rid: runs[rid]["attempt"] for rid in ("d1", "d2", "t1")}, {"d1": 1, "d2": 2, "t1": 1})
        # The commit each step was about: made, tested, merged.
        self.assertEqual(runs["d2"]["step_commit"], "b" * 40)
        self.assertEqual(runs["t1"]["step_commit"], "b" * 40)
        self.assertEqual(runs["m1"]["step_commit"], "c" * 40)
        self.assertIsNone(runs["m1"]["commit_sha"])
        # How many tests a test step ran; nothing for the other steps.
        counted = {"tests": 186, "passed": 183, "failed": 3, "skipped": 0,
                   "failed_tests": [{"suite": "tests.test_a.ATests", "name": "test_x"}]}
        self.assertEqual(runs["t1"]["tests"], counted)
        self.assertIsNone(runs["d2"]["tests"])
        self.assertIsNone(runs["m1"]["tests"])
        # The task's own record carries the same counts, for its Overview.
        detail = {r["id"]: r for r in self.get("/api/v1/tasks/t").json()["runs"]}
        self.assertEqual(detail["t1"]["tests"], counted)
        self.assertIsNone(detail["d2"]["tests"])
        self.assertEqual([r["id"] for r in self.get("/api/v1/tasks/t/runs?limit=2&offset=3").json()["runs"]], ["d2", "stop"])

    def test_runs_say_why_they_ended_as_they_did(self) -> None:
        self.task()
        self.add_runs(2)
        run = self.store.get_run("r1")
        run.role_id, run.outcome = "code_reviewer", "steer"
        run.outcome_detail = "The log can still contain the host and port."
        self.store.save_run(run)
        runs = {r["id"]: r for r in self.get("/api/v1/tasks/t/runs").json()["runs"]}
        self.assertEqual(runs["r1"]["outcome_detail"], "The log can still contain the host and port.")
        self.assertIsNone(runs["r0"]["outcome_detail"])

    def sprint_run(self, rid: str, task_id: str, minute: int, **kw) -> None:
        fields = dict(
            id=rid, task_id=task_id, project_id="p", role_id="developer", workflow_step="develop",
            agent_backend="claude_code", status="completed", outcome="done", model="m",
            cost_usd=0.1, token_count=1, duration_ms=1000,
            started_at=f"2026-01-01T00:{minute:02d}:00Z", completed_at=f"2026-01-01T00:{minute:02d}:00Z",
            created_at=f"2026-01-01T00:{minute:02d}:00Z",
        )
        fields.update(kw)
        self.store.save_run(Run(**fields))

    def test_a_sprints_activity_is_what_happened_to_its_tasks_newest_first(self) -> None:
        self.task("t", task_key="P-1")
        self.task("u", task_key="P-2")
        self.store.save_sprint(Sprint(id="other", project_id="p", title="O", status="planned"))
        self.store.save_task(Task(id="v", sprint_id="other", project_id="p", title="Elsewhere", status="todo"))
        gate = dict(role_id="_builtin:human_gate", workflow_step="merge_approval", model=None)
        # Left out: filing, marking done, gates no person decided.
        self.sprint_run("r-file", "t", 0, role_id="human", workflow_step="file", agent_backend="cli", outcome="file")
        self.sprint_run("r-dev", "t", 1)
        self.sprint_run("r-steer", "t", 2, role_id="code_reviewer", workflow_step="review",
                        outcome="steer", outcome_detail="Fix the log.")
        self.sprint_run("r-asked", "t", 3, agent_backend="builtin", outcome="paused", **gate)
        self.sprint_run("r-approved", "t", 4, agent_backend="human", outcome="approve", **gate)
        self.sprint_run("r-auto", "u", 5, agent_backend="builtin", outcome="approve", **gate)
        self.sprint_run("r-test", "u", 6, role_id="_builtin:run_tests", workflow_step="test",
                        agent_backend="builtin", outcome="failure")
        self.sprint_run("r-done", "t", 7, role_id="_builtin:mark_done", workflow_step="done",
                        agent_backend="builtin", outcome="success")
        self.sprint_run("r-killed", "u", 8, status="killed", outcome="error")
        self.sprint_run("r-cancel-record", "u", 10, role_id="human", workflow_step="cancel",
                        agent_backend="cli", outcome="cancel")
        self.sprint_run("r-elsewhere", "v", 11)
        # What a person did by hand is listed with who and why.
        self.store.save_event(Event(id="e-cancel", run_id="r-cancel-record", task_id="u", project_id="p",
                                    event_type="human.task_cancelled", timestamp="2026-01-01T00:10:00Z",
                                    payload={"by": "ana", "reason": "Not needed."}))

        page = self.get("/api/v1/sprints/s/activity").json()
        self.assertEqual([i["id"] for i in page["items"]],
                         ["e-cancel", "r-killed", "r-test", "r-approved", "r-steer", "r-dev"])
        self.assertEqual(page["total"], 6)
        cancel = page["items"][0]
        self.assertEqual((cancel["source"], cancel["outcome"], cancel["actor"], cancel["outcome_detail"]),
                         ("event", "cancelled", "ana", "Not needed."))
        steer = page["items"][4]
        self.assertEqual((steer["source"], steer["task_id"], steer["task_key"], steer["task_title"]),
                         ("run", "t", "P-1", "Task t"))
        self.assertEqual(steer["outcome_detail"], "Fix the log.")

        problems = self.get("/api/v1/sprints/s/activity?only=problems").json()
        self.assertEqual([i["id"] for i in problems["items"]], ["e-cancel", "r-killed", "r-test", "r-steer"])
        self.assertEqual([i["id"] for i in self.get("/api/v1/sprints/s/activity?limit=1&offset=1").json()["items"]],
                         ["r-killed"])
        self.assertEqual(self.get("/api/v1/sprints/s/activity?only=nothing").status_code, 400)

        # Who did each row, and the By filter: a role, the engine, a user.
        self.assertEqual({i["id"]: i["who"] for i in page["items"]},
                         {"e-cancel": "user", "r-killed": "developer", "r-test": "foreman",
                          "r-approved": "user", "r-steer": "code_reviewer", "r-dev": "developer"})
        self.assertEqual(page["who"], ["code_reviewer", "developer", "foreman", "user"])
        by = lambda query: [i["id"] for i in self.get(f"/api/v1/sprints/s/activity?{query}").json()["items"]]
        self.assertEqual(by("by=developer"), ["r-killed", "r-dev"])
        self.assertEqual(by("by=user"), ["e-cancel", "r-approved"])
        self.assertEqual(by("by=foreman"), ["r-test"])
        self.assertEqual(by("by=developer&only=problems"), ["r-killed"])
        narrowed = self.get("/api/v1/sprints/s/activity?by=foreman").json()
        self.assertEqual((narrowed["total"], narrowed["who"]), (1, page["who"]))
        self.assertEqual(self.get("/api/v1/sprints/nope/activity").status_code, 404)


    def test_the_engines_records_on_a_task_are_listed_by_the_sprint_and_the_task(self) -> None:
        # A block and a recovery the engine kept on the task, at the step at
        # hand or at no step: about the task, so on both lists (ADR-0037).
        self.task("t", task_key="P-1")
        engine = dict(role_id="_builtin:orchestrator", agent_backend="orchestrator", model=None,
                      cost_usd=0.0, duration_ms=None)
        self.sprint_run("r-dev", "t", 1)
        self.sprint_run("r-block", "t", 2, outcome="blocked",
                        outcome_detail="Default branch 'main' HEAD changed from 'x' to 'y'.", **engine)
        self.sprint_run("r-recover", "t", 3, workflow_step="orchestrator", outcome="error",
                        outcome_detail="Recovered orphaned task without an active run.", **engine)
        sprint = [i["id"] for i in self.get("/api/v1/sprints/s/activity").json()["items"]]
        task = [r["id"] for r in self.get("/api/v1/tasks/t/runs").json()["runs"]]
        self.assertEqual(sprint, ["r-recover", "r-block", "r-dev"])
        self.assertEqual(task, ["r-recover", "r-block", "r-dev"])
        problems = [i["id"] for i in self.get("/api/v1/sprints/s/activity?only=problems").json()["items"]]
        self.assertEqual(problems, ["r-recover", "r-block"])

    def test_run_output_has_prompt_and_transcript(self) -> None:
        self.task()
        self.store.save_run(Run(
            id="r", task_id="t", project_id="p", role_id="developer", workflow_step="develop",
            agent_backend="claude_code", prompt_text="Do the thing."))
        for n, payload in enumerate([{"stream": "stdout", "line": "hello"}, {"stream": "stderr", "line": "warn"}]):
            self.store.save_event(Event(
                id=f"e{n}", run_id="r", task_id="t", project_id="p", event_type="agent.raw_output",
                timestamp=f"2026-01-01T00:00:0{n}Z", payload=payload))
        body = self.get("/api/v1/runs/r/output?raw=true").json()
        self.assertEqual(body["prompt"], "Do the thing.")
        self.assertEqual([(e["stream"], e["text"]) for e in body["transcript"]],
                         [("stdout", "hello"), ("stderr", "warn")])
        self.assertFalse(body["transcript_truncated"])
        self.assertTrue(body["raw_included"])
        self.assertEqual(self.get("/api/v1/runs/nope/output").status_code, 404)

    def test_run_output_gives_each_events_facts_and_leaves_the_raw_stream_out(self) -> None:
        self.task()
        self.store.save_run(Run(
            id="r", task_id="t", project_id="p", role_id="developer", workflow_step="develop",
            agent_backend="claude_code", prompt_text="Do the thing."))
        recorded = [
            ("agent.raw_output", {"stream": "stdout", "line": '{"type":"assistant"}'}),
            ("agent.command", {"command": "ls", "cwd": "/w"}),
            ("agent.message", {"phase": "assistant", "text": "x" * 5000}),
            ("engine.test_output", {"stream": "stdout", "text": "OK"}),
        ]
        for n, (kind, payload) in enumerate(recorded):
            self.store.save_event(Event(
                id=f"e{n}", run_id="r", task_id="t", project_id="p", event_type=kind,
                timestamp=f"2026-01-01T00:00:0{n}Z", payload=payload))

        body = self.get("/api/v1/runs/r/output").json()

        self.assertEqual(
            [e["kind"] for e in body["transcript"]],
            ["agent.command", "agent.message", "engine.test_output"],
        )
        command, message, test_line = body["transcript"]
        self.assertEqual(command["data"], {"command": "ls", "cwd": "/w"})
        self.assertEqual(command["text"], "")
        # A long string is cut, and says by how much.
        self.assertTrue(message["data"]["text"].endswith("[... 1000 more characters]"))
        self.assertEqual((test_line["text"], test_line["data"]), ("OK", None))
        self.assertEqual((body["raw_entries"], body["raw_included"]), (1, False))

        raw = self.get("/api/v1/runs/r/output?raw=true").json()
        self.assertEqual([e["kind"] for e in raw["transcript"]], ["agent.raw_output"])

    def repo_run(self, run_id: str, step: str, n: int, **kw) -> None:
        fields = dict(
            id=run_id, task_id="t", project_id="p", role_id="developer", workflow_step=step,
            agent_backend="claude_code", created_at=f"2026-01-01T00:00:0{n}Z",
            started_at=f"2026-01-01T00:00:0{n}Z",
        )
        self.store.save_run(Run(**{**fields, **kw}))

    def repo_event(self, run_id: str, kind: str, payload: dict, n: int = 9) -> None:
        self.store.save_event(Event(
            id=f"{run_id}-{kind}", run_id=run_id, task_id="t", project_id="p", event_type=kind,
            timestamp=f"2026-01-01T00:00:0{n}Z", payload=payload))

    def test_a_step_says_its_session_and_what_it_changed_against(self) -> None:
        self.task()
        self.repo_run("r1", "develop", 1, session_id="s-1", commit_sha="c248621")
        self.repo_run("r-review", "review", 2, role_id="code_reviewer", session_id="s-r")
        self.repo_run("r2", "develop", 3, session_id="s-1", commit_sha="d0d0d0d")
        self.repo_run("r3", "develop", 4, session_id="s-other")
        self.repo_run("r-test", "test", 5, role_id="_builtin:test", agent_backend="builtin", session_id="s-1")
        self.repo_event("r1", "engine.step_changes", {
            "from_sha": "0db4ca5", "to_sha": "c248621", "from_default_branch": True,
            "files": [{"path": "assay/serve.py", "added": 300, "removed": 4, "status": "modified"}],
            "files_total": 9, "added": 327, "removed": 4})
        self.repo_event("r2", "engine.step_changes", {
            "from_sha": "c248621", "to_sha": "d0d0d0d",
            "files": [{"path": "assay/serve.py", "added": 46, "removed": 9, "status": "modified"},
                      {"path": "tests/test_serve.py", "added": 24, "removed": 5, "status": "added"}],
            "files_total": 2, "added": 70, "removed": 14})
        self.repo_event("r3", "engine.step_changes", {
            "from_sha": "abcdef0", "to_sha": "d0d0d0e", "files": [], "files_total": 0, "added": 0, "removed": 0})

        first = self.get("/api/v1/runs/r1/output").json()
        second = self.get("/api/v1/runs/r2/output").json()
        third = self.get("/api/v1/runs/r3/output").json()

        self.assertEqual(first["session"], {"continued_from": None, "continued_attempt": None})
        self.assertEqual(second["session"], {"continued_from": "r1", "continued_attempt": 1})
        self.assertEqual(third["session"]["continued_from"], None)
        self.assertIsNone(self.get("/api/v1/runs/r-test/output").json()["session"])
        self.assertEqual(
            first["changes"]["against"], {"kind": "default_branch", "sha": "0db4ca5", "run_id": None, "attempt": None, "branch": "main"}
        )
        self.assertEqual((first["changes"]["files_total"], first["changes"]["added"], first["changes"]["removed"]), (9, 327, 4))
        self.assertEqual(
            second["changes"]["against"], {"kind": "attempt", "sha": "c248621", "run_id": "r1", "attempt": 1, "branch": None}
        )
        self.assertEqual([f["path"] for f in second["changes"]["files"]], ["assay/serve.py", "tests/test_serve.py"])
        self.assertEqual(third["changes"]["against"]["kind"], "commit")

    def test_a_merge_gives_what_it_brought_in_and_an_older_run_gives_none(self) -> None:
        self.task()
        self.repo_run("m", "merge", 1, role_id="_builtin:merge", agent_backend="builtin")
        self.repo_run("m-old", "merge", 2, role_id="_builtin:merge", agent_backend="builtin")
        self.repo_run("old-dev", "develop", 3)
        self.repo_event("m", "engine.merge", {
            "branch": "feat/x", "target": "main", "sha": "c6aa057", "target_before": "0db4ca5",
            "commits": [{"sha": "c248621", "subject": "feat: serve"}, {"sha": "0a5b562", "subject": "fix: serve"}],
            "commits_total": 2,
            "changes": {"files": [], "files_total": 9, "added": 383, "removed": 4}})
        self.repo_event("m-old", "engine.merge", {"branch": "feat/x", "target": "main", "sha": "aaaaaaa"})

        merged = self.get("/api/v1/runs/m/output").json()
        old = self.get("/api/v1/runs/m-old/output").json()
        dev = self.get("/api/v1/runs/old-dev/output").json()

        self.assertEqual(merged["merge"]["target_before"], "0db4ca5")
        self.assertEqual([c["sha"] for c in merged["merge"]["commits"]], ["c248621", "0a5b562"])
        self.assertEqual(merged["merge"]["changes"]["added"], 383)
        self.assertIsNone(merged["session"])
        self.assertIsNone(old["merge"])
        self.assertEqual((dev["changes"], dev["merge"]), (None, None))


    def test_run_output_is_capped(self) -> None:
        self.task()
        self.store.save_run(Run(
            id="r", task_id="t", project_id="p", role_id="developer", workflow_step="develop",
            agent_backend="claude_code", prompt_text="p" * (OUTPUT_CAP_CHARS + 5)))
        chunk = "z" * (OUTPUT_CAP_CHARS // 2)
        for n in range(3):
            self.store.save_event(Event(
                id=f"e{n}", run_id="r", task_id="t", project_id="p", event_type="agent.raw_output",
                timestamp=f"2026-01-01T00:00:0{n}Z", payload={"stream": "stdout", "line": chunk}))
        body = self.get("/api/v1/runs/r/output?raw=true").json()
        self.assertTrue(body["prompt_truncated"])
        self.assertEqual(len(body["prompt"]), OUTPUT_CAP_CHARS)
        self.assertTrue(body["transcript_truncated"])
        self.assertEqual((len(body["transcript"]), body["total_entries"]), (2, 3))
        self.assertEqual(body["cap_chars"], OUTPUT_CAP_CHARS)


if __name__ == "__main__":
    unittest.main()
