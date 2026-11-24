"""A step's repository facts are recorded when it ends (ADR-0040)."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from foreman.domain.models import Task
from foreman.engine import repo_facts
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.engine.results import AgentExecutionResult
from foreman.repo.git import commit_changes, commits_between
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedAgentExecutor


class CommitChangesTests(unittest.TestCase):
    """The git helper, against a temporary repository."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        self.git("init", "-q")
        self.git("checkout", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")

    def git(self, *args: str) -> str:
        done = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True)
        return done.stdout.strip()

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def test_added_modified_deleted_renamed_and_binary_files(self) -> None:
        (self.repo / "keep.txt").write_text("one\ntwo\n")
        (self.repo / "gone.txt").write_text("bye\n")
        (self.repo / "old name.txt").write_text("a\nb\nc\nd\ne\nf\n")
        start = self.commit("chore: start")
        (self.repo / "keep.txt").write_text("one\ntwo\nthree\n")
        (self.repo / "gone.txt").unlink()
        self.git("mv", "old name.txt", "new name.txt")
        (self.repo / "added.txt").write_text("x\ny\n")
        (self.repo / "blob.bin").write_bytes(b"\x00\x01\x02\xff")
        end = self.commit("feat: change")

        changes = {change.path: change for change in commit_changes(self.repo, start, end)}

        self.assertEqual(
            {path: change.status for path, change in changes.items()},
            {
                "keep.txt": "modified",
                "gone.txt": "deleted",
                "new name.txt": "renamed",
                "added.txt": "added",
                "blob.bin": "added",
            },
        )
        self.assertEqual((changes["keep.txt"].added, changes["keep.txt"].deleted), (1, 0))
        self.assertEqual(changes["gone.txt"].deleted, 1)
        self.assertEqual(changes["new name.txt"].old_path, "old name.txt")
        self.assertTrue(changes["blob.bin"].binary)
        self.assertFalse(changes["added.txt"].binary)

    def test_commits_between_are_oldest_first(self) -> None:
        (self.repo / "a").write_text("a")
        start = self.commit("chore: start")
        (self.repo / "b").write_text("b")
        first = self.commit("feat: first")
        (self.repo / "c").write_text("c")
        second = self.commit("feat: second")

        commits = commits_between(self.repo, start, "HEAD")

        self.assertEqual([(c.sha, c.subject) for c in commits], [(first, "feat: first"), (second, "feat: second")])

    def test_the_facts_are_alphabetical_binary_files_have_no_counts_and_the_cap_holds(self) -> None:
        (self.repo / "a").write_text("a")
        start = self.commit("chore: start")
        for n in range(repo_facts.STEP_FILES_CAP + 5):
            (self.repo / f"f{n:03}.txt").write_text("x\n")
        (self.repo / "bin.dat").write_bytes(b"\x00\x00")
        end = self.commit("feat: many")

        facts = repo_facts.changes_between(self.repo, start, end)

        assert facts is not None
        self.assertEqual(len(facts["files"]), repo_facts.STEP_FILES_CAP)
        self.assertEqual(facts["files_total"], repo_facts.STEP_FILES_CAP + 6)
        self.assertEqual(facts["files"][0]["path"], "bin.dat")
        self.assertEqual((facts["files"][0]["added"], facts["files"][0]["removed"]), (None, None))
        self.assertEqual(facts["added"], repo_facts.STEP_FILES_CAP + 5)

    def test_the_merge_commits_cap_holds_and_a_failed_read_leaves_the_field_out(self) -> None:
        (self.repo / "a").write_text("a")
        start = self.commit("chore: start")
        for n in range(repo_facts.MERGE_COMMITS_CAP + 3):
            (self.repo / "a").write_text(str(n))
            self.commit(f"feat: {n}")
        head = self.git("rev-parse", "HEAD")

        facts = repo_facts.merge_facts(self.repo, start, head, head)

        self.assertEqual(len(facts["commits"]), repo_facts.MERGE_COMMITS_CAP)
        self.assertEqual(facts["commits_total"], repo_facts.MERGE_COMMITS_CAP + 3)
        self.assertEqual(facts["commits"][0]["subject"], "feat: 0")
        self.assertEqual(facts["changes"]["files_total"], 1)
        broken = repo_facts.merge_facts(self.repo, "0" * 40, head, head)
        self.assertEqual(broken, {"target_before": "0" * 40})
        self.assertEqual(repo_facts.merge_facts(self.repo, None, head, head), {})


class StepChangesEngineTests(OrchestratorTestCase):
    def developer(self, repo_path: Path, files: dict[str, str] | None):
        def handler(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
            if files:
                for name, text in files.items():
                    self.write_text(self.work_dir(task, repo_path) / name, text)
                self.commit_all(self.work_dir(task, repo_path), "feat: implement the slice")
            return AgentExecutionResult(outcome="done", detail="Implemented.", status="completed")

        return handler

    def run_task(self, repo_path, db_path, developer, *, branch_name=None, before=None):
        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path, branch_name=branch_name)
            if before:
                before(repo_path, task)
            executor = ScriptedAgentExecutor(
                {
                    ("developer", 1): developer,
                    ("code_reviewer", 1): lambda **_: AgentExecutionResult(outcome="approve", detail="APPROVE"),
                }
            )
            ForemanOrchestrator(
                store, roles=self.roles, workflows=self.workflows, agent_executor=executor
            ).run_project(project.id)
            runs = {run.workflow_step: run for run in store.list_runs(task_id=task.id)}
            events = {
                step: [e for e in store.list_events(run_id=run.id)] for step, run in runs.items()
            }
            return runs, events

    def test_a_step_that_commits_records_what_it_changed_and_a_merge_what_it_brought_in(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        main_before = self.git(repo_path, "rev-parse", "main").stdout.strip()

        runs, events = self.run_task(
            repo_path, db_path, self.developer(repo_path, {"feature.txt": "a\nb\n", "ready.txt": "ready\n"})
        )

        changed = [e for e in events["develop"] if e.event_type == "engine.step_changes"]
        self.assertEqual(len(changed), 1)
        payload = changed[0].payload
        self.assertEqual(payload["from_sha"], main_before)
        self.assertEqual(payload["to_sha"], runs["develop"].commit_sha)
        self.assertEqual(
            [(f["path"], f["added"], f["removed"], f["status"]) for f in payload["files"]],
            [("feature.txt", 2, 0, "added"), ("ready.txt", 1, 0, "added")],
        )
        self.assertEqual((payload["files_total"], payload["added"], payload["removed"]), (2, 3, 0))
        self.assertTrue(payload["from_default_branch"])
        # A step that did not commit records none.
        self.assertFalse([e for e in events["review"] if e.event_type == "engine.step_changes"])

        merge = [e for e in events["merge"] if e.event_type == "engine.merge"][-1].payload
        self.assertEqual(merge["target_before"], main_before)
        self.assertEqual(merge["commits_total"], 1)
        self.assertEqual(merge["commits"][0]["subject"], "feat: implement the slice")
        self.assertEqual(
            (merge["changes"]["files_total"], merge["changes"]["added"], merge["changes"]["removed"]),
            (2, 3, 0),
        )

    def test_a_step_that_does_not_commit_records_no_changes(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        _, events = self.run_task(repo_path, db_path, self.developer(repo_path, None))

        self.assertFalse([e for e in events.get("develop", []) if e.event_type == "engine.step_changes"])

    def test_what_a_sync_brings_in_from_the_default_branch_is_not_counted(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        def stale_branch(repo_path: Path, task: Task) -> None:
            self.git(repo_path, "checkout", "-q", "-b", task.branch_name)
            self.write_text(repo_path / "own.txt", "own\n")
            self.commit_all(repo_path, "feat: own work")
            self.git(repo_path, "checkout", "-q", "main")
            self.write_text(repo_path / "notes.txt", "main moved\n")
            self.commit_all(repo_path, "docs: main moves forward")

        runs, events = self.run_task(
            repo_path,
            db_path,
            self.developer(repo_path, {"dev.txt": "dev\n", "ready.txt": "ready\n"}),
            branch_name="feat/task-1",
            before=stale_branch,
        )

        self.assertTrue([e for e in events["develop"] if e.event_type == "engine.branch_sync"])
        payload = [e for e in events["develop"] if e.event_type == "engine.step_changes"][0].payload
        self.assertEqual([f["path"] for f in payload["files"]], ["dev.txt", "ready.txt"])

    def test_a_failed_git_read_does_not_fail_the_step(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with mock.patch.object(repo_facts, "commit_changes", side_effect=OSError("no git")):
            runs, events = self.run_task(
                repo_path, db_path, self.developer(repo_path, {"ready.txt": "ready\n"})
            )

        self.assertEqual(runs["develop"].outcome, "done")
        self.assertEqual(runs["merge"].outcome, "success")
        self.assertFalse([e for e in events["develop"] if e.event_type == "engine.step_changes"])
        merge = [e for e in events["merge"] if e.event_type == "engine.merge"][-1].payload
        self.assertIn("target_before", merge)
        self.assertNotIn("changes", merge)


if __name__ == "__main__":
    unittest.main()
