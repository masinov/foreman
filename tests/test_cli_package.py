"""The CLI package: command registration, JSON output and the error boundary."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from foreman.cli import build_parser, main
from foreman.errors import ForemanError
from foreman.models import Project, Sprint, Task
from foreman.store import ForemanStore

COMMANDS_IN_HELP_ORDER = [
    "init", "projects", "project", "sprint", "task", "worktree", "token", "notify",
    "run", "serve", "engine", "status", "board", "watch", "cost", "history",
    "transcript", "approve", "deny", "waive-merge", "revoke-waiver", "roles",
    "workflows", "config", "db", "dashboard",
]


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CommandRegistrationTests(unittest.TestCase):
    def test_every_command_registers_itself_in_the_documented_order(self) -> None:
        parser = build_parser()
        subparsers = next(
            action for action in parser._actions if hasattr(action, "choices") and action.choices
        )

        self.assertEqual(list(subparsers.choices), COMMANDS_IN_HELP_ORDER)

    def test_every_leaf_command_has_a_handler(self) -> None:
        def leaves(parser, path=()):
            # Sub-command groups, not options that merely have choices.
            nested = [
                action for action in parser._actions if isinstance(action.choices, dict)
            ]
            if not nested:
                yield path, parser
                return
            for action in nested:
                for name, child in action.choices.items():
                    yield from leaves(child, (*path, name))

        missing = [
            " ".join(path)
            for path, parser in leaves(build_parser())
            if path and parser.get_default("handler") is None
        ]
        self.assertEqual(missing, [])


class JsonOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db = str(Path(self._temp.name) / "foreman.db")
        with ForemanStore(self.db) as store:
            store.initialize()
            store.save_project(
                Project(id="p1", name="Demo", repo_path=self._temp.name, workflow_id="development")
            )
            store.save_sprint(Sprint(id="s1", project_id="p1", title="First", status="active"))
            store.save_task(
                Task(id="t1", sprint_id="s1", project_id="p1", title="Do it", status="blocked",
                     blocked_reason="waiting")
            )

    def json(self, *argv: str) -> dict:
        code, out, err = run(*argv, "--db", self.db, "--json")
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_projects(self) -> None:
        payload = self.json("projects")

        self.assertEqual([p["id"] for p in payload["projects"]], ["p1"])
        self.assertEqual(payload["projects"][0]["active_sprint_id"], "s1")
        self.assertEqual(payload["projects"][0]["task_counts"]["blocked"], 1)

    def test_sprint_list(self) -> None:
        payload = self.json("sprint", "list", "p1")

        self.assertEqual(payload["project_id"], "p1")
        self.assertEqual(payload["sprints"][0]["status"], "active")
        self.assertEqual(payload["sprints"][0]["task_counts"]["blocked"], 1)

    def test_task_list(self) -> None:
        payload = self.json("task", "list", "p1")

        task = payload["tasks"][0]
        self.assertEqual(task["id"], "t1")
        self.assertEqual(task["status"], "blocked")
        self.assertEqual(task["blocked_reason"], "waiting")
        self.assertTrue(task["key"])

    def test_engine_status(self) -> None:
        payload = self.json("engine", "status", "p1")

        self.assertEqual(payload["state"], "stopped")
        self.assertFalse(payload["resident"])
        self.assertEqual(payload["commands"], [])

    def test_without_the_flag_the_output_is_the_text_it_always_was(self) -> None:
        code, out, _ = run("projects", "--db", self.db)

        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("Projects\n"))


class ErrorBoundaryTests(unittest.TestCase):
    def test_an_error_foreman_raised_is_one_line_and_exit_1(self) -> None:
        with mock.patch("foreman.cli.catalog.handle_roles", side_effect=ForemanError("no such thing")):
            code, out, err = run("roles")

        self.assertEqual(code, 1)
        self.assertEqual(err, "foreman: no such thing\n")
        self.assertNotIn("Traceback", err)

    def test_a_bug_is_reported_without_a_traceback_and_exits_70(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FOREMAN_DEBUG", None)
            with mock.patch("foreman.cli.catalog.handle_roles", side_effect=KeyError("oops")):
                code, _, err = run("roles")

        self.assertEqual(code, 70)
        self.assertIn("unexpected error (KeyError)", err)
        self.assertIn("FOREMAN_DEBUG=1", err)
        self.assertNotIn("Traceback", err)

    def test_the_traceback_is_available_on_request(self) -> None:
        with mock.patch.dict(os.environ, {"FOREMAN_DEBUG": "1"}):
            with mock.patch("foreman.cli.catalog.handle_roles", side_effect=KeyError("oops")):
                with self.assertRaises(KeyError):
                    run("roles")

    def test_an_interrupt_exits_130(self) -> None:
        with mock.patch("foreman.cli.catalog.handle_roles", side_effect=KeyboardInterrupt):
            code, _, err = run("roles")

        self.assertEqual(code, 130)


if __name__ == "__main__":
    unittest.main()
