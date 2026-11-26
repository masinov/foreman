"""A merge commit carries the task's key, title and change file's text (ADR-0040)."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.domain.models import Project, Task
from foreman.engine.builtins.merge import _merge_message
from foreman.repo.git import merge_branch, read_file_at


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


class MergeMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        for args in (("init", "-q"), ("checkout", "-q", "-b", "main"),
                     ("config", "user.email", "t@example.com"), ("config", "user.name", "T")):
            git(self.repo, *args)
        (self.repo / "a.txt").write_text("a\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        (self.repo / "changes").mkdir()
        (self.repo / "changes" / "P-5.md").write_text("# Cards rank\n\n- A card shows its rank.\n", encoding="utf-8")
        (self.repo / "b.txt").write_text("b\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "work")
        git(self.repo, "checkout", "-q", "main")
        self.project = Project(id="p", name="P", repo_path=str(self.repo), workflow_id="d", default_branch="main")

    def task(self, key: str = "P-5") -> Task:
        return Task(id="t", sprint_id="s", project_id="p", title="Rank the cards", task_key=key, branch_name="feat/x")

    def test_the_message_is_the_key_and_title_then_the_change(self) -> None:
        self.assertEqual(
            _merge_message(self.project, self.task()),
            "Merge P-5: Rank the cards\n\n# Cards rank\n\n- A card shows its rank.",
        )

    def test_a_branch_without_a_change_file_gets_the_subject_only(self) -> None:
        self.assertEqual(_merge_message(self.project, self.task("P-6")), "Merge P-6: Rank the cards")
        self.assertIsNone(read_file_at(self.repo, "feat/x", "changes/P-6.md"))

    def test_the_commit_carries_it_with_and_without_a_finishing_step(self) -> None:
        message = _merge_message(self.project, self.task())
        result = merge_branch(self.repo, "feat/x", "main", message=message)
        self.assertTrue(result.success, result.detail)
        self.assertEqual(git(self.repo, "log", "-1", "--format=%B"), message)
        git(self.repo, "reset", "-q", "--hard", "HEAD^")
        result = merge_branch(self.repo, "feat/x", "main", message=message, finish=lambda tree: None)
        self.assertTrue(result.success, result.detail)
        self.assertEqual(git(self.repo, "log", "-1", "--format=%B"), message)


if __name__ == "__main__":
    unittest.main()
