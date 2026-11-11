"""The git helpers the engine relies on, against real repositories."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.git import (
    GitError,
    branch_exists,
    commits_behind,
    current_branch,
    head_sha,
    is_worktree_clean,
    merge_branch,
    merge_in_progress,
    merge_preflight,
    run_git,
    sync_branch_with_base,
    task_commits_on_default_branch,
    worktree_branch,
)


class GitHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.repo = Path(self._temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("checkout", "-q", "-b", "main")
        self.git("config", "user.email", "git-tests@example.com")
        self.git("config", "user.name", "Git Tests")
        self.commit("README.md", "# repo\n", "chore: initial commit")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.repo, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def commit(self, name: str, content: str, message: str) -> str:
        (self.repo / name).write_text(content, encoding="utf-8")
        self.git("add", name)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def branch(self, name: str, *, from_ref: str = "main") -> None:
        self.git("checkout", "-q", "-b", name, from_ref)

    # ── reading state ────────────────────────────────────────────────────

    def test_head_sha_branch_exists_and_current_branch(self) -> None:
        sha = self.git("rev-parse", "HEAD")

        self.assertEqual(head_sha(self.repo), sha)
        self.assertEqual(head_sha(self.repo, "refs/heads/main"), sha)
        self.assertIsNone(head_sha(self.repo, "refs/heads/nope"))
        self.assertTrue(branch_exists(self.repo, "main"))
        self.assertFalse(branch_exists(self.repo, "nope"))
        self.assertEqual(current_branch(self.repo), "main")
        self.assertEqual(worktree_branch(self.repo), "main")

    def test_a_detached_head_has_no_worktree_branch(self) -> None:
        self.git("checkout", "-q", "--detach")

        self.assertIsNone(worktree_branch(self.repo))

    def test_is_worktree_clean_sees_modified_staged_and_untracked_files(self) -> None:
        self.assertTrue(is_worktree_clean(self.repo))
        (self.repo / "new.txt").write_text("x", encoding="utf-8")
        self.assertFalse(is_worktree_clean(self.repo))
        self.git("add", "new.txt")
        self.assertFalse(is_worktree_clean(self.repo))
        self.git("commit", "-q", "-m", "feat: new")
        self.assertTrue(is_worktree_clean(self.repo))
        (self.repo / "README.md").write_text("changed", encoding="utf-8")
        self.assertFalse(is_worktree_clean(self.repo))

    def test_run_git_raises_on_failure_unless_told_not_to(self) -> None:
        with self.assertRaises(GitError):
            run_git(self.repo, "rev-parse", "no-such-ref")
        result = run_git(self.repo, "rev-parse", "no-such-ref", check=False)
        self.assertNotEqual(result.returncode, 0)

    def test_commits_behind_counts_what_the_branch_lacks(self) -> None:
        self.branch("feat/a")
        self.git("checkout", "-q", "main")
        self.commit("one.txt", "1", "feat: one")
        self.commit("two.txt", "2", "feat: two")

        self.assertEqual(commits_behind(self.repo, "feat/a", "main"), 2)
        self.assertEqual(commits_behind(self.repo, "main", "feat/a"), 0)
        self.assertEqual(commits_behind(self.repo, "nope", "main"), 0)

    # ── merging ──────────────────────────────────────────────────────────

    def test_merge_branch_merges_and_leaves_the_target_checked_out(self) -> None:
        self.branch("feat/a")
        self.commit("feature.py", "x = 1\n", "feat: a")

        result = merge_branch(self.repo, "feat/a", "main")

        self.assertTrue(result.success, result.detail)
        self.assertFalse(result.conflict)
        self.assertEqual(current_branch(self.repo), "main")
        self.assertTrue((self.repo / "feature.py").is_file())
        self.assertIn("Merge branch 'feat/a'", self.git("log", "-1", "--format=%s"))

    def test_a_conflicting_merge_is_reported_and_leaves_no_merge_in_progress(self) -> None:
        self.branch("feat/a")
        self.commit("README.md", "# theirs\n", "feat: theirs")
        self.git("checkout", "-q", "main")
        ours = self.commit("README.md", "# ours\n", "feat: ours")

        result = merge_branch(self.repo, "feat/a", "main")

        self.assertFalse(result.success)
        self.assertTrue(result.conflict)
        self.assertFalse(merge_in_progress(self.repo))
        self.assertTrue(is_worktree_clean(self.repo))
        self.assertEqual(head_sha(self.repo), ours)

    def test_merge_in_progress_is_true_only_while_a_merge_is_unconcluded(self) -> None:
        self.branch("feat/a")
        self.commit("README.md", "# theirs\n", "feat: theirs")
        self.git("checkout", "-q", "main")
        self.commit("README.md", "# ours\n", "feat: ours")
        self.assertFalse(merge_in_progress(self.repo))

        subprocess.run(["git", "merge", "feat/a"], cwd=self.repo, capture_output=True)

        self.assertTrue(merge_in_progress(self.repo))
        self.git("merge", "--abort")
        self.assertFalse(merge_in_progress(self.repo))

    def test_sync_branch_with_base_brings_the_base_into_the_branch(self) -> None:
        self.branch("feat/a")
        self.commit("feature.py", "x = 1\n", "feat: a")
        self.git("checkout", "-q", "main")
        self.commit("base.py", "y = 2\n", "feat: base moved")

        result = sync_branch_with_base(self.repo, "feat/a", "main")

        self.assertTrue(result.success, result.detail)
        self.assertEqual(current_branch(self.repo), "feat/a")
        self.assertTrue((self.repo / "base.py").is_file())
        self.assertEqual(commits_behind(self.repo, "feat/a", "main"), 0)

    def test_a_conflicting_sync_is_aborted_and_reported(self) -> None:
        self.branch("feat/a")
        head = self.commit("README.md", "# theirs\n", "feat: theirs")
        self.git("checkout", "-q", "main")
        self.commit("README.md", "# ours\n", "feat: ours")

        result = sync_branch_with_base(self.repo, "feat/a", "main")

        self.assertFalse(result.success)
        self.assertTrue(result.conflict)
        self.assertFalse(merge_in_progress(self.repo))
        self.assertEqual(head_sha(self.repo, "refs/heads/feat/a"), head)

    # ── preflight ────────────────────────────────────────────────────────

    def test_merge_preflight_names_what_is_wrong(self) -> None:
        self.branch("feat/a")
        self.commit("feature.py", "x = 1\n", "feat: a")
        self.git("checkout", "-q", "main")

        def reason(**kwargs: str) -> str | None:
            result = merge_preflight(self.repo, **kwargs)
            return None if result.success else result.reason

        self.assertIsNone(reason(source_branch="feat/a", target_branch="main"))
        self.assertEqual(reason(source_branch="nope", target_branch="main"), "missing_source")
        self.assertEqual(reason(source_branch="feat/a", target_branch="nope"), "missing_target")
        self.assertEqual(reason(source_branch="main", target_branch="main"), "same_branch")
        (self.repo / "README.md").write_text("dirty", encoding="utf-8")
        self.assertEqual(reason(source_branch="feat/a", target_branch="main"), "dirty_worktree")

    # ── what may be on the default branch ────────────────────────────────

    def test_a_tasks_own_commit_on_the_default_branch_is_found(self) -> None:
        seen = head_sha(self.repo, "refs/heads/main")
        self.branch("feat/a")
        leaked = self.commit("feature.py", "x = 1\n", "feat: a")
        self.git("checkout", "-q", "main")

        self.assertEqual(
            task_commits_on_default_branch(
                self.repo, task_branch="feat/a", default_branch="main", default_shas_seen=(seen,)
            ),
            (),
        )
        self.git("merge", "-q", "--ff-only", "feat/a")
        self.assertEqual(
            task_commits_on_default_branch(
                self.repo, task_branch="feat/a", default_branch="main", default_shas_seen=(seen,)
            ),
            (leaked,),
        )

    def test_the_default_branch_moving_on_its_own_is_not_the_tasks_doing(self) -> None:
        seen = head_sha(self.repo, "refs/heads/main")
        self.branch("feat/a")
        self.commit("feature.py", "x = 1\n", "feat: a")
        self.git("checkout", "-q", "main")
        self.commit("other.py", "y = 2\n", "feat: someone else's work")

        self.assertEqual(
            task_commits_on_default_branch(
                self.repo, task_branch="feat/a", default_branch="main", default_shas_seen=(seen,)
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
