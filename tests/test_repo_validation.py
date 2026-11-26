"""The repository validator asks a branch for its own change file (ADR-0040)."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from repo_validation import branch_changes, validate_repo_scaffold  # noqa: E402


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


class BranchChangeFileTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        for args in (("init", "-q"), ("checkout", "-q", "-b", "main"),
                     ("config", "user.email", "t@example.com"), ("config", "user.name", "T")):
            git(self.repo, *args)
        (self.repo / "changes").mkdir()
        (self.repo / "changes" / "FOR-1.md").write_text("Old change\n", encoding="utf-8")
        (self.repo / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "checkout", "-q", "-b", "feat/x")

    def commit(self, name: str, text: str) -> None:
        (self.repo / name).write_text(text, encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", name)

    def issues(self) -> list[str]:
        return [issue.path for issue in validate_repo_scaffold(self.repo, branch_name="feat/x")
                if issue.path in {"changes", "CHANGELOG.md"}]

    def test_a_change_file_already_on_main_is_not_the_branchs(self) -> None:
        self.commit("code.py", "x = 1\n")
        self.assertEqual(branch_changes(self.repo), {"code.py"})
        self.assertEqual(self.issues(), ["changes"])

    def test_the_branchs_own_change_file_passes(self) -> None:
        self.commit("changes/FOR-2.md", "New change\n")
        self.assertEqual(self.issues(), [])

    def test_a_branch_that_edits_the_changelog_is_named(self) -> None:
        self.commit("changes/FOR-2.md", "New change\n")
        self.commit("CHANGELOG.md", "# Changelog\n\n- by hand\n")
        self.assertEqual(self.issues(), ["CHANGELOG.md"])


if __name__ == "__main__":
    unittest.main()
