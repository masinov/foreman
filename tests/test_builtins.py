from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from foreman.engine.builtins import BuiltinExecutor
from foreman.domain.models import Project, Task


def _run(directory: Path, command: str, **settings: object):
    project = Project(
        id="p",
        name="P",
        repo_path=str(directory),
        workflow_id="development",
        settings={"test_command": command, **settings},
    )
    result = BuiltinExecutor()._run_tests(project=project, working_dir=directory)
    run_event = next(e for e in result.events if e.event_type == "engine.test_run")
    return result, run_event.payload


class RunTestsReportTests(unittest.TestCase):
    def test_success_reports_summary_line_and_tail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, payload = _run(Path(temp_dir), "echo hello")
        self.assertEqual(result.outcome, "success")
        first, blank, rest = result.detail.split("\n", 2)
        self.assertRegex(first, r"^Tests passed in \d+\.\ds \(exit 0\)\.$")
        self.assertEqual(blank, "")
        self.assertEqual(rest, "hello")
        self.assertIsInstance(payload["duration_seconds"], float)
        self.assertGreaterEqual(payload["duration_seconds"], 0.0)

    def test_failure_reports_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, payload = _run(Path(temp_dir), "echo boom; exit 3")
        self.assertEqual(result.outcome, "failure")
        lines = result.detail.split("\n")
        self.assertRegex(lines[0], r"^Tests failed in \d+\.\ds \(exit 3\)\.$")
        self.assertEqual(lines[1:], ["", "boom"])
        self.assertEqual(payload["exit_code"], 3)

    def test_silent_success_has_only_summary_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, _ = _run(Path(temp_dir), "true")
        self.assertRegex(result.detail, r"^Tests passed in \d+\.\ds \(exit 0\)\.$")

    def test_timeout_keeps_existing_sentence_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, payload = _run(
                Path(temp_dir), "echo started; sleep 30", test_timeout_seconds=1
            )
        self.assertEqual(result.outcome, "failure")
        self.assertTrue(
            result.detail.startswith("Test command timed out after 1s and was killed.")
        )
        self.assertTrue(payload["timed_out"])
        self.assertGreaterEqual(payload["duration_seconds"], 1.0)

    def test_head_sha_matches_repository_head(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            git = ["git", "-c", "user.name=T", "-c", "user.email=t@example.com"]
            subprocess.run([*git, "init", "-q"], cwd=directory, check=True)
            subprocess.run(
                [*git, "commit", "-q", "--allow-empty", "-m", "init"], cwd=directory, check=True
            )
            expected = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=directory,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            _, payload = _run(directory, "true")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{40,64}", expected))
        self.assertEqual(payload["head_sha"], expected)

    def test_head_sha_is_null_outside_a_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, payload = _run(Path(temp_dir), "true")
        self.assertIsNone(payload["head_sha"])

    def test_missing_command_keeps_early_return(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, payload = _run(Path(temp_dir), "")
        self.assertEqual(result.detail, "Project test_command is not configured.")
        self.assertNotIn("duration_seconds", payload)


if __name__ == "__main__":
    unittest.main()


class MergeBranchBehindTests(unittest.TestCase):
    """ADR-0026: the merge built-in does not merge a branch behind the default branch."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        self.worktree = root / "task-tree"
        self.git(self.repo, "init")
        self.git(self.repo, "checkout", "-b", "main")
        self.git(self.repo, "config", "user.email", "t@example.com")
        self.git(self.repo, "config", "user.name", "T")
        self.write("base.txt", "base\n")
        self.commit("chore: base")
        self.git(self.repo, "worktree", "add", "-b", "feat/x", str(self.worktree))
        self.write("feature.txt", "feature\n", self.worktree)
        self.commit("feat: feature", self.worktree)
        self.project = Project(
            id="p",
            name="P",
            repo_path=str(self.repo),
            workflow_id="development",
            default_branch="main",
            settings={"completion_guard_enabled": False},
        )
        self.task = Task(
            id="t", sprint_id="s", project_id="p", title="T", status="in_progress",
            branch_name="feat/x", worktree_path=str(self.worktree),
        )

    def git(self, cwd: Path, *args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
        if done.returncode != 0:
            raise AssertionError(f"git {args} failed: {done.stderr}")
        return done.stdout.strip()

    def write(self, name: str, text: str, where: Path | None = None) -> None:
        (where or self.repo).joinpath(name).write_text(text, encoding="utf-8")

    def commit(self, message: str, where: Path | None = None) -> None:
        self.git(where or self.repo, "add", ".")
        self.git(where or self.repo, "commit", "-m", message)

    def merge(self):
        return BuiltinExecutor().execute(
            "_builtin:merge",
            project=self.project,
            task=self.task,
            step_id="merge",
            carried_output=None,
            store=None,
        )

    def test_behind_branch_is_updated_in_its_worktree_and_not_merged(self) -> None:
        self.write("other.txt", "other\n")
        self.commit("feat: main moves")
        main_head = self.git(self.repo, "rev-parse", "main")
        checked_out = self.git(self.repo, "branch", "--show-current")

        result = self.merge()

        self.assertEqual(result.outcome, "updated")
        self.assertEqual(self.git(self.repo, "rev-parse", "main"), main_head)
        self.git(self.repo, "merge-base", "--is-ancestor", main_head, "feat/x")
        self.assertEqual(self.git(self.repo, "branch", "--show-current"), checked_out)
        self.assertEqual(self.git(self.worktree, "branch", "--show-current"), "feat/x")
        self.assertFalse((self.repo / "feature.txt").exists())
        event = next(e for e in result.events if e.event_type == "engine.branch_sync")
        self.assertEqual(event.payload["step"], "merge")
        self.assertEqual(event.payload["branch"], "feat/x")
        self.assertEqual(event.payload["target"], "main")
        self.assertEqual(event.payload["commits_behind"], 1)
        self.assertIn("mode", event.payload)

    def test_conflicting_behind_branch_gets_conflict_and_main_is_unchanged(self) -> None:
        self.write("feature.txt", "main version\n")
        self.commit("feat: main edits the same file")
        main_head = self.git(self.repo, "rev-parse", "main")

        result = self.merge()

        self.assertEqual(result.outcome, "conflict")
        self.assertIn("Merge conflict against 'main'.", result.detail)
        self.assertEqual(self.git(self.repo, "rev-parse", "main"), main_head)
        self.assertEqual(self.git(self.worktree, "status", "--porcelain"), "")

    def test_branch_that_is_not_behind_merges_as_before(self) -> None:
        result = self.merge()

        self.assertEqual(result.outcome, "success")
        self.assertFalse(
            [e for e in result.events if e.event_type == "engine.branch_sync"]
        )
        self.assertEqual(self.git(self.repo, "show", "main:feature.txt"), "feature")


class UpdatedOutcomeWiringTests(unittest.TestCase):
    def test_outcome_is_named_everywhere_and_shipped_workflows_carry_it(self) -> None:
        from foreman.dashboard_definitions import _OUTCOME_ORDER
        from foreman.domain.outcomes import CANONICAL_OUTCOMES, normalize_agent_outcome
        from foreman.definitions.workflows import _BUILTIN_OUTCOMES, load_workflow

        self.assertIn("updated", _BUILTIN_OUTCOMES["_builtin:merge"])
        self.assertIn("updated", _OUTCOME_ORDER)
        self.assertIn("updated", CANONICAL_OUTCOMES)
        self.assertEqual(normalize_agent_outcome("updated"), "updated")
        base = Path(__file__).resolve().parent.parent / "foreman" / "data" / "workflows"
        for name in ("development", "development_tiered", "development_secure"):
            workflow = load_workflow(base / f"{name}.toml")
            transition = workflow.find_transition("merge", "updated")
            self.assertIsNotNone(transition, name)
            self.assertEqual(transition.to_step, "test", name)
