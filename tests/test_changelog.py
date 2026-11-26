"""``CHANGELOG.md`` generated from ``changes/`` when a sprint finishes (ADR-0040)."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.cli import main
from foreman.domain.models import Event, Project, Sprint, Task
from foreman.domain.settings import ProjectSettings, SettingsError
from foreman.engine.sprints import SprintFlow
from foreman.history.records import RunRecords
from foreman.mutations import Mutations
from foreman.mutations.changelog import MARKER, Change, fold_section, parse_change, read_changes, render_section
from foreman.notifications.delivery import NotificationDispatcher
from foreman.store import ForemanStore

OLD = "# Changelog\n\nIntro line.\n\n## [Unreleased]\n\n- An old entry.\n"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


class ChangelogTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.repo = root / "repo"
        (self.repo / "changes").mkdir(parents=True)
        for args in (("init", "-q"), ("checkout", "-q", "-b", "main"),
                     ("config", "user.email", "t@example.com"), ("config", "user.name", "T")):
            git(self.repo, *args)
        (self.repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        (self.repo / "CHANGELOG.md").write_text(OLD, encoding="utf-8")
        (self.repo / "changes" / "README.md").write_text("How to write one.\n", encoding="utf-8")
        (self.repo / "changes" / "P-10.md").write_text("Rank the evidence\n\n- Claims are ranked.\n", encoding="utf-8")
        (self.repo / "changes" / "P-2.md").write_text("# Claim card\n\n- A card per claim.\n- It shows its source.\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")
        self.store = ForemanStore(root / "foreman.db")
        self.store.initialize()
        self.addCleanup(self.store.close)

    def project(self, **settings: object) -> Project:
        project = Project(id="p", name="P", repo_path=str(self.repo), workflow_id="development",
                          default_branch="main", settings=dict(settings))
        self.store.save_project(project)
        return project

    def sprint(self) -> Sprint:
        sprint = Sprint(id="s", project_id="p", title="Weight of evidence", status="active")
        self.store.save_sprint(sprint)
        self.store.save_task(Task(id="t1", sprint_id="s", project_id="p", title="Claim card", status="done", task_key="P-2"))
        return sprint

    def events(self, kind: str) -> list[Event]:
        return self.store.list_sprint_events("s", event_types=[kind])

    def assert_folded(self) -> None:
        text = (self.repo / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(MARKER, text)
        self.assertIn("## Weight of evidence (", text)
        # Each change under its task key, in key order (P-2 before P-10).
        self.assertLess(text.index("### P-2: Claim card"), text.index("### P-10: Rank the evidence"))
        self.assertIn("- A card per claim.\n- It shows its source.", text)
        # What the file held stays below the generated sections.
        self.assertLess(text.index("## Weight of evidence"), text.index("## [Unreleased]"))
        self.assertTrue(text.startswith("# Changelog\n\nIntro line.\n"))
        self.assertTrue(text.endswith("- An old entry.\n"))
        self.assertFalse((self.repo / "changes" / "P-2.md").exists())
        self.assertFalse((self.repo / "changes" / "P-10.md").exists())
        self.assertTrue((self.repo / "changes" / "README.md").exists())

    def test_a_user_finishing_a_sprint_commits_the_changelog_with_the_note(self) -> None:
        self.project(generate_changelog=True, write_checkpoint_notes=True)
        self.sprint()
        before = git(self.repo, "rev-parse", "main")
        Mutations(self.store, via="cli").transition_sprint(self.store.get_sprint("s"), "completed")
        (event,) = self.events("engine.checkpoint")
        head = git(self.repo, "rev-parse", "main")
        # One commit holds the note, the changelog and the removals; the tag is on it.
        self.assertEqual(git(self.repo, "rev-parse", f"{head}^"), before)
        self.assertEqual(git(self.repo, "rev-parse", f"{event.payload['tag']}^{{commit}}"), head)
        changed = set(git(self.repo, "show", "--name-status", "--format=", head).splitlines())
        self.assertEqual({line.split("\t")[0] for line in changed}, {"A", "M", "D"})
        self.assertEqual(event.payload["changelog_path"], "CHANGELOG.md")
        self.assert_folded()
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_the_engine_finishing_a_sprint_writes_it_too(self) -> None:
        project = self.project(generate_changelog=True, sprint_completion="auto")
        sprint = self.sprint()
        records = RunRecords(self.store, NotificationDispatcher(self.store))
        flow = SprintFlow(self.store, records, lambda: datetime(2026, 11, 23, 12, tzinfo=timezone.utc))
        self.assertEqual(flow.resolve(project, sprint), "idle")
        (event,) = self.events("engine.checkpoint")
        self.assertIsNone(event.payload["note_path"])
        self.assertEqual(git(self.repo, "rev-parse", f"{event.payload['tag']}^{{commit}}"), git(self.repo, "rev-parse", "main"))
        self.assertIn("## Weight of evidence (2026-11-23)", (self.repo / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assert_folded()

    def test_a_changelog_that_cannot_be_written_is_recorded_and_the_sprint_stays_finished(self) -> None:
        self.project(generate_changelog=True)
        self.sprint()
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho no commits today >&2\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        before = git(self.repo, "rev-parse", "main")
        sprint = Mutations(self.store, via="cli").transition_sprint(self.store.get_sprint("s"), "completed")
        self.assertEqual(sprint.status, "completed")
        self.assertEqual(self.store.get_sprint("s").status, "completed")
        (event,) = self.events("engine.checkpoint_failed")
        self.assertIn("could not commit the changelog", event.payload["reason"])
        self.assertIn("no commits today", event.payload["reason"])
        self.assertEqual(self.events("engine.checkpoint"), [])
        # Nothing is lost: the file and the change files are as they were.
        self.assertEqual(git(self.repo, "rev-parse", "main"), before)
        self.assertEqual((self.repo / "CHANGELOG.md").read_text(encoding="utf-8"), OLD)
        self.assertTrue((self.repo / "changes" / "P-2.md").exists())
        integration = self.repo / ".foreman" / "worktrees" / "_integration"
        if integration.exists():
            self.assertEqual(git(integration, "status", "--porcelain"), "")

    def test_a_project_that_does_not_turn_it_on_is_left_as_it_is(self) -> None:
        self.project()
        self.sprint()
        before = git(self.repo, "rev-parse", "main")
        Mutations(self.store, via="cli").transition_sprint(self.store.get_sprint("s"), "completed")
        self.assertEqual(git(self.repo, "rev-parse", "main"), before)
        self.assertEqual((self.repo / "CHANGELOG.md").read_text(encoding="utf-8"), OLD)
        self.assertTrue((self.repo / "changes" / "P-2.md").exists())

    def test_no_change_files_writes_nothing(self) -> None:
        self.project(generate_changelog=True)
        self.sprint()
        git(self.repo, "rm", "-q", "changes/P-2.md", "changes/P-10.md")
        git(self.repo, "commit", "-q", "-m", "drop")
        before = git(self.repo, "rev-parse", "main")
        Mutations(self.store, via="cli").transition_sprint(self.store.get_sprint("s"), "completed")
        (event,) = self.events("engine.checkpoint")
        self.assertIsNone(event.payload["changelog_path"])
        self.assertEqual(git(self.repo, "rev-parse", "main"), before)

    def test_the_command_writes_the_changelog_by_hand(self) -> None:
        self.project(generate_changelog=True)
        sprint = self.sprint()
        # Finished without a checkpoint, as an engine older than the changelog would.
        sprint.status, sprint.completed_at = "completed", "2026-11-26T21:06:54Z"
        self.store.save_sprint(sprint)
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["changelog", "p", "--db", str(self.store.db_path)])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("Wrote CHANGELOG.md for Weight of evidence", out.getvalue())
        self.assert_folded()
        again = io.StringIO()
        with redirect_stdout(again):
            self.assertEqual(main(["changelog", "p", "--db", str(self.store.db_path)]), 0)
        self.assertIn("nothing written", again.getvalue())

    def test_the_command_waits_for_the_active_sprint_to_finish(self) -> None:
        self.project(generate_changelog=True)
        self.sprint()
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["changelog", "p", "--db", str(self.store.db_path)])
        self.assertEqual(code, 1)
        self.assertIn("is active", err.getvalue())
        self.assertTrue((self.repo / "changes" / "P-2.md").exists())

    def test_a_change_file_that_is_not_text_is_recorded_and_the_tree_left_clean(self) -> None:
        self.project(generate_changelog=True, write_checkpoint_notes=True)
        self.sprint()
        (self.repo / "changes" / "P-3.md").write_bytes(b"\xff\xfe not text\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "bad change file")
        Mutations(self.store, via="cli").transition_sprint(self.store.get_sprint("s"), "completed")
        self.assertEqual(self.store.get_sprint("s").status, "completed")
        (event,) = self.events("engine.checkpoint_failed")
        self.assertIn("could not be written", event.payload["reason"])
        integration = self.repo / ".foreman" / "worktrees" / "_integration"
        self.assertEqual(git(integration, "status", "--porcelain"), "")

    def test_a_note_and_a_changelog_that_cannot_be_committed_leave_the_tree_clean(self) -> None:
        self.project(generate_changelog=True, write_checkpoint_notes=True)
        self.sprint()
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        Mutations(self.store, via="cli").transition_sprint(self.store.get_sprint("s"), "completed")
        self.assertTrue(self.events("engine.checkpoint_failed"))
        integration = self.repo / ".foreman" / "worktrees" / "_integration"
        self.assertEqual(git(integration, "status", "--porcelain"), "")

    def test_the_command_refuses_a_project_that_has_not_turned_it_on(self) -> None:
        self.project()
        self.sprint()
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["changelog", "p", "--db", str(self.store.db_path)])
        self.assertEqual(code, 1)
        self.assertIn("generate_changelog=true", err.getvalue())
        self.assertTrue((self.repo / "changes" / "P-2.md").exists())

    def test_the_setting_is_true_or_false(self) -> None:
        self.assertFalse(ProjectSettings.from_raw({}).generate_changelog)
        self.assertTrue(ProjectSettings.from_raw({"generate_changelog": True}).generate_changelog)
        with self.assertRaises(SettingsError):
            ProjectSettings.from_raw({"generate_changelog": "yes"})

    def test_a_change_file_is_a_title_then_bullets(self) -> None:
        change = parse_change("FOR-1", "# Title here\n\n- one\n- two that\n  wraps\n", "changes/FOR-1.md")
        self.assertEqual(change, Change("FOR-1", "Title here", ("one", "two that wraps"), "changes/FOR-1.md"))
        self.assertEqual(read_changes(self.repo)[0].key, "P-2")

    def test_folding_into_an_existing_section_goes_first(self) -> None:
        sprint = Sprint(id="s", project_id="p", title="Two", status="completed")
        moment = datetime(2026, 11, 26, tzinfo=timezone.utc)
        first = fold_section(OLD, render_section(Sprint(id="o", project_id="p", title="One", status="completed"), moment, [Change("A-1", "a", ("x",), "")]))
        both = fold_section(first, render_section(sprint, moment, [Change("A-2", "b", ("y",), "")]))
        self.assertEqual(both.count(MARKER), 1)
        self.assertLess(both.index("## Two"), both.index("## One"))
        self.assertLess(both.index("## One"), both.index("## [Unreleased]"))


if __name__ == "__main__":
    unittest.main()
