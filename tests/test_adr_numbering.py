"""An ADR is numbered when it merges, and its index is generated (ADR-0040)."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.domain.models import Project, Task
from foreman.domain.settings import ProjectSettings, SettingsError
from foreman.engine.builtins import BuiltinExecutor
from foreman.repo.adrs import MARKER, Adr, render_index, title_and_status

INTRO = "# ADRs\n\nHow to add a decision: write docs/adr/new-<slug>.md.\n\n## Index\n\n| ADR | Title | Status |\n|---|---|---|\n| ADR-0001 | Old | accepted |\n"
ADR_1 = "# ADR-0001: First Decision\n\n- Status: accepted\n"
ADR_2 = "# ADR-0002: Second Decision\n\n- **Status:** superseded by ADR-0003 (the owner, today)\n"


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise AssertionError(f"git {args} failed: {done.stderr}")
    return done.stdout.strip()


class AdrIndexTests(unittest.TestCase):
    def test_title_and_status_cut_the_parenthesis(self) -> None:
        self.assertEqual(title_and_status(ADR_2), ("Second Decision", "superseded by ADR-0003"))
        self.assertEqual(title_and_status("# ADR-0002: Old Form\n\n## Status\n\nAccepted\n"), ("Old Form", "accepted"))
        self.assertEqual(title_and_status("# Plain title\n\nStatus: proposed\n"), ("Plain title", "proposed"))

    def test_the_hand_written_part_is_kept_and_the_list_replaced(self) -> None:
        adrs = [Adr(1, "ADR-0001-a.md", "First", "accepted"), Adr(2, "ADR-0002-b.md", "Second", "proposed")]
        first = render_index(INTRO, adrs)
        self.assertTrue(first.startswith("# ADRs\n\nHow to add a decision"))
        self.assertIn("| ADR-0002 | Second | proposed |", first)
        self.assertNotIn("| Old |", first)
        self.assertEqual(render_index(first, adrs), first)
        again = render_index(first, adrs[:1])
        self.assertIn(MARKER, again)
        self.assertNotIn("Second", again)


class AdrMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "repo"
        (self.repo / "docs" / "adr").mkdir(parents=True)
        for args in (("init", "-q"), ("checkout", "-q", "-b", "main"),
                     ("config", "user.email", "t@example.com"), ("config", "user.name", "T")):
            git(self.repo, *args)
        (self.repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        self.write(self.repo, "docs/adr/README.md", INTRO)
        self.write(self.repo, "docs/adr/ADR-0001-first.md", ADR_1)
        self.write(self.repo, "docs/adr/ADR-0002-second.md", ADR_2)
        self.commit(self.repo, "chore: base")

    def write(self, where: Path, name: str, text: str) -> None:
        path = where / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, where: Path, message: str) -> None:
        git(where, "add", "-A")
        git(where, "commit", "-q", "-m", message)

    def branch(self, name: str, files: dict[str, str]) -> Task:
        tree = self.root / name.replace("/", "-")
        git(self.repo, "worktree", "add", "-q", "-b", name, str(tree), "main")
        for path, text in files.items():
            self.write(tree, path, text)
        self.commit(tree, f"feat: {name}")
        return Task(id=name, sprint_id="s", project_id="p", title=name, status="in_progress",
                    branch_name=name, worktree_path=str(tree))

    def merge(self, task: Task, **settings: object):
        project = Project(id="p", name="P", repo_path=str(self.repo), workflow_id="development",
                          default_branch="main",
                          settings={"completion_guard_enabled": False, **settings})
        return BuiltinExecutor().execute("_builtin:merge", project=project, task=task,
                                         step_id="merge", carried_output=None, store=None)

    def on_main(self, path: str) -> str:
        return git(self.repo, "show", f"main:{path}")

    def decision(self, title: str) -> str:
        return f"# ADR-XXXX: {title}\n\n- Status: accepted\n\nSee ADR-XXXX itself.\n"

    def test_a_new_file_is_numbered_with_references_and_index(self) -> None:
        task = self.branch("feat/a", {
            "docs/adr/new-cache.md": self.decision("Cache Things"),
            "docs/NOTES.md": "Read docs/adr/new-cache.md and [it](adr/new-cache.md).\n",
        })
        result = self.merge(task)

        self.assertEqual(result.outcome, "success", result.detail)
        self.assertIn("Numbered docs/adr/new-cache.md as docs/adr/ADR-0003-cache.md", result.detail)
        names = git(self.repo, "ls-tree", "--name-only", "main", "docs/adr/").splitlines()
        self.assertIn("docs/adr/ADR-0003-cache.md", names)
        self.assertNotIn("docs/adr/new-cache.md", names)
        text = self.on_main("docs/adr/ADR-0003-cache.md")
        self.assertTrue(text.startswith("# ADR-0003: Cache Things"))
        self.assertIn("See ADR-0003 itself.", text)
        self.assertEqual(self.on_main("docs/NOTES.md"),
                         "Read docs/adr/ADR-0003-cache.md and [it](adr/ADR-0003-cache.md).")
        index = self.on_main("docs/adr/README.md")
        self.assertIn("How to add a decision", index)
        self.assertIn("| ADR-0003 | Cache Things | accepted |", index)
        self.assertIn("| ADR-0002 | Second Decision | superseded by ADR-0003 |", index)
        self.assertNotIn("| Old |", index)
        # One merge commit: the branch's own commits are not rewritten.
        self.assertEqual(git(self.repo, "show", "--no-patch", "--format=%P", "main").count(" "), 1)
        self.assertEqual(git(self.repo, "show", "feat/a:docs/adr/new-cache.md"), self.decision("Cache Things").strip())
        merge_event = next(e for e in result.events if e.event_type == "engine.merge")
        self.assertEqual(merge_event.payload["adrs"], [["docs/adr/new-cache.md", "docs/adr/ADR-0003-cache.md"]])

    def test_two_branches_get_different_numbers(self) -> None:
        first = self.branch("feat/a", {"docs/adr/new-one.md": self.decision("One")})
        second = self.branch("feat/b", {"docs/adr/new-two.md": self.decision("Two")})

        self.assertEqual(self.merge(first).outcome, "success")
        # The second is now behind and is brought up to date, as ADR-0026 says.
        self.assertEqual(self.merge(second).outcome, "updated")
        self.assertEqual(self.merge(second).outcome, "success")

        names = git(self.repo, "ls-tree", "--name-only", "main", "docs/adr/").splitlines()
        self.assertIn("docs/adr/ADR-0003-one.md", names)
        self.assertIn("docs/adr/ADR-0004-two.md", names)
        index = self.on_main("docs/adr/README.md")
        self.assertIn("| ADR-0003 | One | accepted |", index)
        self.assertIn("| ADR-0004 | Two | accepted |", index)

    def test_a_duplicate_number_is_refused_and_named(self) -> None:
        task = self.branch("feat/a", {"docs/adr/ADR-0002-other.md": "# ADR-0002: Other\n\n- Status: accepted\n"})
        before = git(self.repo, "rev-parse", "main")

        result = self.merge(task)

        self.assertEqual(result.outcome, "blocked")
        self.assertIn("ADR-0002", result.detail)
        self.assertIn("ADR-0002-other.md", result.detail)
        self.assertIn("ADR-0002-second.md", result.detail)
        self.assertEqual(git(self.repo, "rev-parse", "main"), before)
        self.assertEqual(git(self.integration(), "status", "--porcelain"), "")
        event = next(e for e in result.events if e.event_type == "engine.merge_blocked")
        self.assertEqual(event.payload["reason"], "duplicate_adr_numbers")
        self.assertEqual(event.payload["duplicates"][0]["number"], 2)

    def test_a_duplicate_already_on_the_default_branch_is_refused(self) -> None:
        self.write(self.repo, "docs/adr/ADR-0001-again.md", ADR_1)
        self.commit(self.repo, "chore: hand-numbered clash")
        task = self.branch("feat/a", {"docs/adr/new-x.md": self.decision("X")})
        result = self.merge(task)
        self.assertEqual(result.outcome, "blocked")
        self.assertIn("ADR-0001-again.md", result.detail)
        self.assertIn("ADR-0001-first.md", result.detail)

    def test_a_merge_without_decisions_is_as_before(self) -> None:
        task = self.branch("feat/a", {"other.txt": "x\n"})
        before = self.on_main("docs/adr/README.md")
        self.assertEqual(self.merge(task).outcome, "success")
        self.assertEqual(self.on_main("docs/adr/README.md"), before)
        self.assertEqual(self.on_main("other.txt"), "x")

    def test_a_project_without_the_folder_or_with_it_off_is_left_alone(self) -> None:
        task = self.branch("feat/a", {"docs/adr/new-cache.md": self.decision("Cache")})
        self.assertEqual(self.merge(task, adr_dir="").outcome, "success")
        self.assertIn("docs/adr/new-cache.md", git(self.repo, "ls-tree", "-r", "--name-only", "main"))
        other = self.branch("feat/b", {"notes/new-thing.md": "# Thing\n"})
        self.assertEqual(self.merge(other).outcome, "success")
        self.assertIn("notes/new-thing.md", git(self.repo, "ls-tree", "-r", "--name-only", "main"))

    def integration(self) -> Path:
        return self.repo / ".foreman" / "worktrees" / "_integration"

    def test_two_new_decisions_in_one_branch_that_name_each_other(self) -> None:
        task = self.branch("feat/a", {
            "docs/adr/new-alpha.md": "# ADR-XXXX: Alpha\n\n- Status: accepted\n\nSee new-beta.md.\n",
            "docs/adr/new-beta.md": "# ADR-XXXX: Beta\n\n- Status: accepted\n\nAfter docs/adr/new-alpha.md.\n",
        })
        result = self.merge(task)
        self.assertEqual(result.outcome, "success", result.detail)
        self.assertIn("See ADR-0004-beta.md.", self.on_main("docs/adr/ADR-0003-alpha.md"))
        self.assertIn("After docs/adr/ADR-0003-alpha.md.", self.on_main("docs/adr/ADR-0004-beta.md"))
        self.assertEqual(git(self.integration(), "status", "--porcelain"), "")
        # The next merge is not held up by anything left behind.
        self.assertEqual(self.merge(self.branch("feat/b", {"other.txt": "x\n"})).outcome, "success")

    def test_a_decision_that_is_not_text_is_refused_and_the_tree_left_clean(self) -> None:
        task = self.branch("feat/a", {"docs/adr/new-bin.md": "x"})
        tree = self.root / "feat-a"
        (tree / "docs/adr/new-bin.md").write_bytes(b"# ADR-XXXX: \xff\xfe\n")
        self.commit(tree, "feat: not text")
        result = self.merge(task)
        self.assertEqual(result.outcome, "blocked")
        self.assertIn("not UTF-8", result.detail)
        self.assertEqual(git(self.integration(), "status", "--porcelain"), "")
        self.assertEqual(self.merge(self.branch("feat/b", {"other.txt": "x\n"})).outcome, "success")

    def test_a_merge_whose_numbering_fails_is_undone(self) -> None:
        from unittest import mock

        task = self.branch("feat/a", {"docs/adr/new-x.md": self.decision("X")})
        with mock.patch("foreman.engine.builtins.merge.settle", side_effect=RuntimeError("boom")):
            result = self.merge(task)
        self.assertNotEqual(result.outcome, "success")
        self.assertIn("boom", result.detail)
        self.assertEqual(git(self.integration(), "status", "--porcelain"), "")
        self.assertEqual(self.merge(task).outcome, "success")

    def test_only_the_branchs_files_and_only_the_decision_are_rewritten(self) -> None:
        self.write(self.repo, "other/notes.md", "See other/new-api.md and new-api.md.\n")
        self.commit(self.repo, "chore: unrelated notes")
        task = self.branch("feat/a", {
            "docs/adr/new-api.md": self.decision("API"),
            "docs/GUIDE.md": "Read adr/new-api.md, not other/new-api.md.\n",
        })
        self.assertEqual(self.merge(task).outcome, "success")
        self.assertEqual(self.on_main("other/notes.md"), "See other/new-api.md and new-api.md.")
        self.assertEqual(self.on_main("docs/GUIDE.md"), "Read adr/ADR-0003-api.md, not other/new-api.md.")

    def test_a_branch_without_decisions_merges_without_the_commit_hook(self) -> None:
        plain = self.branch("feat/a", {"other.txt": "x\n"})
        numbered = self.branch("feat/b", {"docs/adr/new-x.md": self.decision("X")})
        hooks = self.repo / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        self.assertEqual(self.merge(plain).outcome, "success")
        # A branch with a decision is committed as a plain merge would be.
        outcomes = [self.merge(numbered).outcome for _ in range(2)]
        self.assertIn("success", outcomes)

    def test_the_folder_is_a_setting(self) -> None:
        self.assertEqual(ProjectSettings.from_raw({}).adr_dir, "docs/adr")
        self.assertEqual(ProjectSettings.from_raw({"adr_dir": "decisions/"}).adr_dir, "decisions")
        self.assertEqual(ProjectSettings.from_raw({"adr_dir": ""}).adr_dir, "")
        for bad in ("/etc", "../x", 3):
            with self.assertRaises(SettingsError):
                ProjectSettings.from_raw({"adr_dir": bad})


if __name__ == "__main__":
    unittest.main()
