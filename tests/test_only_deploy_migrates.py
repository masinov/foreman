"""Only `foreman db migrate` migrates; code in a worktree cannot reach the live database."""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from foreman.cli import main
from foreman.cli.common import DB_ENV, discover_repo_local_db_path, resolve_db_path
from foreman.runner.env import agent_environment
from foreman.store import ForemanStore
from foreman.store.base import _SCHEMA_MIGRATIONS_DDL
from foreman.store.migrations import MIGRATIONS

LATEST = max(m[0] for m in MIGRATIONS)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cli(*argv: str) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, err.getvalue() + out.getvalue()


class RefusedAtAnotherVersionTests(unittest.TestCase):
    def _database(self, tmp: str, kind: str) -> Path:
        path = Path(tmp) / "f.db"
        with ForemanStore(path) as store:
            store.upgrade()
            if kind == "older":
                store._connection.execute(
                    "DELETE FROM schema_migrations WHERE version = ?", (LATEST,)
                )
            else:
                store._connection.execute(
                    "INSERT INTO schema_migrations (version, description, applied_at)"
                    " VALUES (?, 'future', 'now')",
                    (LATEST + 1,),
                )
            store._connection.commit()
        return path

    def test_commands_refuse_and_change_nothing_in_both_directions(self) -> None:
        commands = (
            ("backlog", "list", "p"),
            ("run", "p"),
            ("task", "show", "t"),
        )
        for kind, wanted in (("older", "foreman db migrate"), ("newer", "Upgrade Foreman")):
            for command in commands:
                with self.subTest(kind=kind, command=command), tempfile.TemporaryDirectory() as tmp:
                    path = self._database(tmp, kind)
                    before = _digest(path)
                    code, text = _cli(*command, "--db", str(path))
                    self.assertEqual(code, 1)
                    self.assertIn(kind, text)
                    self.assertIn(wanted, text)
                    self.assertEqual(_digest(path), before)

    def test_a_new_database_is_created_at_the_latest_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with ForemanStore(Path(tmp) / "new.db") as store:
                self.assertEqual(store.initialize(), [v for v, _, _ in sorted(MIGRATIONS)])
                self.assertEqual(store.schema_version(), LATEST)

    def test_an_old_database_with_tables_but_no_ledger_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.db"
            with ForemanStore(path) as store:
                store._connection.execute("CREATE TABLE tasks (id TEXT)")
                store._connection.commit()
            before = _digest(path)
            with ForemanStore(path) as store:
                from foreman.store import SchemaVersionError

                with self.assertRaises(SchemaVersionError):
                    store.initialize()
            self.assertEqual(_digest(path), before)

    def test_db_migrate_is_the_path_that_migrates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._database(tmp, "older")
            code, _ = _cli("backlog", "list", "p", "--db", str(path))
            self.assertEqual(code, 1)
            with ForemanStore(path) as store:
                self.assertEqual(store.schema_version(), LATEST - 1)
            code, text = _cli("db", "migrate", "--db", str(path))
            self.assertEqual(code, 0, text)
            with ForemanStore(path) as store:
                self.assertEqual(store.schema_version(), LATEST)

    def test_db_migrate_refuses_a_newer_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._database(tmp, "newer")
            before = _digest(path)
            code, text = _cli("db", "migrate", "--db", str(path))
            self.assertEqual(code, 1)
            self.assertIn("Upgrade Foreman", text)
            self.assertEqual(_digest(path), before)


class DatabaseDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.main = Path(self._temp.name).resolve() / "main"
        (self.main / ".git").mkdir(parents=True)
        (self.main / ".foreman.db").write_bytes(b"")
        (self.main / "src" / "pkg").mkdir(parents=True)

    def _worktree(self, name: str) -> Path:
        tree = self.main / ".foreman" / "worktrees" / name
        tree.mkdir(parents=True)
        (tree / ".git").write_text("gitdir: ../../../.git/worktrees/x\n")  # a file, as git writes it
        (tree / "sub").mkdir()
        return tree

    def test_a_subdirectory_of_the_main_checkout_finds_its_database(self) -> None:
        found = discover_repo_local_db_path(self.main / "src" / "pkg")
        self.assertEqual(found, self.main / ".foreman.db")

    def test_a_task_worktree_does_not_find_the_main_checkouts_database(self) -> None:
        tree = self._worktree("FOR-1")
        self.assertIsNone(discover_repo_local_db_path(tree))
        self.assertIsNone(discover_repo_local_db_path(tree / "sub"))

    def test_a_sandbox_clone_does_not_find_it_either(self) -> None:
        sandbox = self.main / ".foreman" / "worktrees" / "review" / "clone"
        (sandbox / ".git").mkdir(parents=True)
        self.assertIsNone(discover_repo_local_db_path(sandbox))

    def test_a_command_in_a_worktree_has_no_database_unless_given_one(self) -> None:
        from foreman.cli.common import CliResolutionError

        tree = self._worktree("FOR-2")
        env = {k: v for k, v in os.environ.items() if k != DB_ENV}
        with mock.patch.dict(os.environ, env, clear=True), contextlib.chdir(tree):
            with self.assertRaises(CliResolutionError):
                resolve_db_path(None)
            code, text = _cli("backlog", "list", "p")
        self.assertEqual(code, 1)
        self.assertNotIn(str(self.main / ".foreman.db"), text.replace("worktrees", ""))
        # Asked for explicitly, it is still reachable.
        explicit = resolve_db_path(str(self.main / ".foreman.db"))
        self.assertEqual(explicit, self.main / ".foreman.db")

    def test_a_command_in_the_main_checkout_subdirectory_resolves_it(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != DB_ENV}
        with mock.patch.dict(os.environ, env, clear=True), contextlib.chdir(self.main / "src"):
            self.assertEqual(resolve_db_path(None), self.main / ".foreman.db")


class AgentEnvironmentTests(unittest.TestCase):
    def test_an_agent_step_carries_no_foreman_db(self) -> None:
        host = {"PATH": "/bin", "HOME": "/h", DB_ENV: "/live/.foreman.db"}
        self.assertNotIn(DB_ENV, agent_environment(host=host))
        with mock.patch.dict(os.environ, {DB_ENV: "/live/.foreman.db"}):
            self.assertNotIn(DB_ENV, agent_environment())


class ServeRefusalLogTests(unittest.TestCase):
    def test_the_refusal_is_written_to_the_workers_log(self) -> None:
        import argparse

        from foreman.cli.common import EXIT_SCHEMA_REFUSED
        from foreman.cli.engine import handle_serve

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".foreman.db"
            with ForemanStore(path) as store:
                store._connection.executescript(_SCHEMA_MIGRATIONS_DDL)
                store._connection.commit()
            args = argparse.Namespace(db=str(path), project_id="p", poll_seconds=1.0, once=True)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(handle_serve(args), EXIT_SCHEMA_REFUSED)
            log = (Path(tmp) / ".foreman" / "serve.log").read_text()
            self.assertIn("foreman db migrate", log)


if __name__ == "__main__":
    unittest.main()
