"""``foreman task edit`` changes type and texts; commands take a task's key."""

from __future__ import annotations

import contextlib
import io
import os
import stat
import sys
import textwrap
from pathlib import Path
from unittest import mock

from foreman.cli import main
from foreman.manager import agent as manager_agent
from foreman.domain.models import Project
from foreman.store import ForemanStore

from tests.test_task_edit import _Workspace


class TaskTextEditTests(_Workspace):
    def setUp(self) -> None:
        super().setUp()
        for project_id in ("p1", "p2"):
            project = self.store.get_project(project_id)
            project.task_key_prefix = "KEY"
            self.store.save_project(project)

    def run_cli(self, *argv: str, stdin: str | None = None, tty: bool = False) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        patches = [contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)]
        if stdin is not None:
            patches.append(mock.patch.object(sys, "stdin", io.StringIO(stdin)))
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            stack.enter_context(mock.patch("foreman.cli.tasks.texts.is_terminal", return_value=tty))
            code = main([*argv, "--db", str(self.db_path)])
        return code, out.getvalue(), err.getvalue()

    def reread(self, task_id: str):
        store = ForemanStore(self.db_path)
        self.addCleanup(store.close)
        task = store.get_task(task_id)
        assert task is not None
        return task

    def editor(self, body: str) -> Path:
        path = Path(self._temp.name) / "editor.py"
        path.write_text(f"#!{sys.executable}\nimport sys\n{textwrap.dedent(body)}")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return path

    # The three ways -------------------------------------------------------

    def test_type_and_both_texts_on_the_command_line(self) -> None:
        self.task("t1")
        code, out, err = self.run_cli(
            "task", "edit", "t1", "--type", "fix", "--description", "Why", "--criteria", "It works"
        )
        self.assertEqual(code, 0, err)
        task = self.reread("t1")
        self.assertEqual((task.task_type, task.description, task.acceptance_criteria), ("fix", "Why", "It works"))
        self.assertIn("Type: feature -> fix", out)
        self.assertIn("Description: set (3 characters)", out)
        self.assertNotIn("It works", out)

    def test_texts_from_a_file_and_from_the_pipe(self) -> None:
        self.task("t1", description="old")
        path = Path(self._temp.name) / "d.md"
        path.write_text("From a file\n")
        code, out, err = self.run_cli("task", "edit", "t1", "--description-file", str(path))
        self.assertEqual(code, 0, err)
        self.assertIn("Description: changed", out)
        code, _, err = self.run_cli(
            "task", "edit", "t1", "--criteria-file", "-", stdin="Line one\nLine two\n"
        )
        self.assertEqual(code, 0, err)
        task = self.reread("t1")
        self.assertEqual(task.description, "From a file")
        self.assertEqual(task.acceptance_criteria, "Line one\nLine two")
        code, _, err = self.run_cli("task", "edit", "t1", "--description-file", "/nope/x")
        self.assertEqual(code, 1)
        self.assertIn("Could not read", err)

    def test_an_empty_text_clears_it_as_the_dashboard_does(self) -> None:
        self.task("t1", description="old")
        code, out, _ = self.run_cli("task", "edit", "t1", "--description", "")
        self.assertEqual(code, 0)
        self.assertIn("Description: cleared", out)
        self.assertFalse(self.reread("t1").description)

    # --edit ---------------------------------------------------------------

    def test_edit_stores_what_the_editor_leaves(self) -> None:
        self.task("t1", description="old text")
        script = self.editor(
            """
            text = open(sys.argv[1]).read()
            open(sys.argv[1], "w").write(text + " and more\\n")
            """
        )
        with mock.patch.dict(os.environ, {"VISUAL": str(script)}):
            code, out, err = self.run_cli("task", "edit", "t1", "--edit", "description", tty=True)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.reread("t1").description, "old text and more")
        self.assertIn("Description: changed", out)
        # The temporary file is gone afterwards.
        seen = list(Path(os.environ.get("TMPDIR", "/tmp")).glob("foreman-description-*"))
        self.assertEqual(seen, [])

    def test_edit_uses_editor_when_visual_is_unset(self) -> None:
        self.task("t1")
        script = self.editor('open(sys.argv[1], "w").write("via EDITOR")')
        env = {k: v for k, v in os.environ.items() if k not in ("VISUAL", "EDITOR")}
        env["EDITOR"] = str(script)
        with mock.patch.dict(os.environ, env, clear=True):
            code, _, err = self.run_cli("task", "edit", "t1", "--edit", "criteria", tty=True)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.reread("t1").acceptance_criteria, "via EDITOR")

    def test_edit_unchanged_or_emptied_changes_nothing_and_says_so(self) -> None:
        self.task("t1", description="keep me")
        for body in ("pass", 'open(sys.argv[1], "w").write("  \\n")'):
            script = self.editor(body)
            with mock.patch.dict(os.environ, {"VISUAL": str(script)}):
                code, out, err = self.run_cli("task", "edit", "t1", "--edit", "description", tty=True)
            self.assertEqual(code, 0, err)
            self.assertIn("Description unchanged.", out)
            self.assertEqual(self.reread("t1").description, "keep me")

    def test_edit_refuses_without_a_terminal_and_never_starts_the_editor(self) -> None:
        self.task("t1")
        script = self.editor('open("/dev/null")')
        with mock.patch.dict(os.environ, {"VISUAL": str(script)}), mock.patch(
            "foreman.cli.tasks.texts.subprocess.run"
        ) as run:
            code, _, err = self.run_cli("task", "edit", "t1", "--edit", "description", tty=False)
        self.assertEqual(code, 1)
        self.assertIn("--description-file -", err)
        run.assert_not_called()

    # Refusals -------------------------------------------------------------

    def test_conflicting_options_are_refused(self) -> None:
        self.task("t1")
        for argv in (
            ("--description", "x", "--description-file", "-"),
            ("--criteria", "x", "--criteria-file", "-"),
            ("--edit", "description", "--description", "x"),
            ("--edit", "criteria", "--criteria-file", "-"),
            ("--description-file", "-", "--criteria-file", "-"),
        ):
            code, _, err = self.run_cli("task", "edit", "t1", *argv, stdin="x", tty=True)
            self.assertEqual(code, 1, argv)
            self.assertTrue(err, argv)
        task = self.reread("t1")
        self.assertFalse(task.description)

    # History --------------------------------------------------------------

    def test_changes_to_a_running_task_are_recorded_via_cli(self) -> None:
        self.task("t1", status="in_progress")
        code, _, err = self.run_cli(
            "task", "edit", "t1", "--type", "fix", "--description-file", "-", stdin="New why"
        )
        self.assertEqual(code, 0, err)
        events = [e for e in self.store.list_events(task_id="t1") if e.event_type == "human.task_edited"]
        self.assertEqual(len(events), 1)
        payload = events[0].payload
        self.assertEqual(payload["changed_fields"], {"task_type": "fix", "description": "New why"})
        self.assertEqual(payload["via"], "cli")

    # Keys -----------------------------------------------------------------

    def test_commands_take_a_key(self) -> None:
        self.task("t1")
        key = self.reread("t1").task_key
        self.assertTrue(key.startswith("KEY-"))
        code, out, err = self.run_cli("task", "show", key)
        self.assertEqual(code, 0, err)
        self.assertIn("Task: t1", out)
        code, _, err = self.run_cli("task", "edit", key.lower(), "--title", "Renamed")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.reread("t1").title, "Renamed")
        code, _, err = self.run_cli("task", "block", key, "--reason", "waiting")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.reread("t1").status, "blocked")
        code, _, err = self.run_cli("history", key)
        self.assertEqual(code, 0, err)
        code, _, err = self.run_cli("task", "show", "KEY-999")
        self.assertEqual(code, 1)
        self.assertIn("Unknown task: KEY-999", err)

    def test_a_key_in_two_projects_is_refused_naming_them(self) -> None:
        self.task("t1")
        self.task("t2", sprint="s2", project="p2")
        self.assertEqual(self.reread("t1").task_key, self.reread("t2").task_key)
        code, _, err = self.run_cli("task", "show", self.reread("t1").task_key)
        self.assertEqual(code, 1)
        self.assertIn("p1", err)
        self.assertIn("p2", err)
        self.assertIn("id", err)

    def test_the_manager_contract_names_the_options_and_keys(self) -> None:
        contract = manager_agent.build_operating_contract(
            Project(id="p1", name="P", repo_path="/r", workflow_id="development")
        )
        for words in ("--description-file -", "--criteria-file -", "--edit", "--type", "key"):
            self.assertIn(words, contract)
