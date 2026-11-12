"""A task's changes, diff, checks and runs (sprint 58 slice 7)."""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import tempfile
import unittest

import httpx

from foreman.dashboard.app import create_dashboard_app
from foreman.dashboard.task_models import DIFF_CAP_CHARS, OUTPUT_CAP_CHARS
from foreman.models import CompletionEvidence, Event, Project, Run, Sprint, Task
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
            judged_by="judge-model",
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
                     "head_sha": head, "output_tail": "collected\n12 passed in 3.1s\n"}))
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
        self.assertEqual(body["claims"]["judged_by"], "judge-model")
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
        self.assertEqual(body["claims"]["judged_by"], "none")
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
        self.assertEqual(self.get("/api/v1/tasks/t/runs?limit=0").status_code, 400)
        self.assertEqual(self.get("/api/v1/tasks/nope/runs").status_code, 404)

    def test_run_output_has_prompt_and_transcript(self) -> None:
        self.task()
        self.store.save_run(Run(
            id="r", task_id="t", project_id="p", role_id="developer", workflow_step="develop",
            agent_backend="claude_code", prompt_text="Do the thing."))
        for n, payload in enumerate([{"stream": "stdout", "line": "hello"}, {"stream": "stderr", "line": "warn"}]):
            self.store.save_event(Event(
                id=f"e{n}", run_id="r", task_id="t", project_id="p", event_type="agent.raw_output",
                timestamp=f"2026-01-01T00:00:0{n}Z", payload=payload))
        body = self.get("/api/v1/runs/r/output").json()
        self.assertEqual(body["prompt"], "Do the thing.")
        self.assertEqual([(e["stream"], e["text"]) for e in body["transcript"]],
                         [("stdout", "hello"), ("stderr", "warn")])
        self.assertFalse(body["transcript_truncated"])
        self.assertEqual(self.get("/api/v1/runs/nope/output").status_code, 404)

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
        body = self.get("/api/v1/runs/r/output").json()
        self.assertTrue(body["prompt_truncated"])
        self.assertEqual(len(body["prompt"]), OUTPUT_CAP_CHARS)
        self.assertTrue(body["transcript_truncated"])
        self.assertEqual((len(body["transcript"]), body["total_entries"]), (2, 3))
        self.assertEqual(body["cap_chars"], OUTPUT_CAP_CHARS)


if __name__ == "__main__":
    unittest.main()
