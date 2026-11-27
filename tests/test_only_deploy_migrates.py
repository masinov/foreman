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
from foreman.store.base import _SCHEMA_MIGRATIONS_DDL
from foreman.store.migrations import MIGRATIONS

LATEST = max(m[0] for m in MIGRATIONS)


@contextlib.contextmanager
def _chdir(path: Path):
    """``contextlib.chdir``, which Python 3.10 (in CI) does not have."""

    before = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(before)


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
            if kind == "older":
                # A database made by the release before: its last migration
                # was never run (deleting its ledger row would leave its
                # changes in the tables, and run it twice).
                store._connection.executescript(_SCHEMA_MIGRATIONS_DDL)
                store.migrate(sorted(MIGRATIONS)[: LATEST - 1])
            else:
                store.upgrade()
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
        live = self.main / ".foreman.db"
        with ForemanStore(live) as store:
            store.initialize()
        before = _digest(live)
        env = {k: v for k, v in os.environ.items() if k != DB_ENV}
        with mock.patch.dict(os.environ, env, clear=True), _chdir(tree):
            with self.assertRaises(CliResolutionError):
                resolve_db_path(None)
            code, text = _cli("backlog", "list", "p")
        self.assertEqual(code, 1)
        # Refused for being in a worktree, not for a project missing from the
        # live database it reached.
        self.assertIn("out of its reach on purpose", text)
        self.assertEqual(_digest(live), before)
        # Asked for explicitly, it is still reachable.
        explicit = resolve_db_path(str(self.main / ".foreman.db"))
        self.assertEqual(explicit, self.main / ".foreman.db")

    def test_a_command_in_the_main_checkout_subdirectory_resolves_it(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != DB_ENV}
        with mock.patch.dict(os.environ, env, clear=True), _chdir(self.main / "src"):
            self.assertEqual(resolve_db_path(None), self.main / ".foreman.db")


class RuntimeDirectoryDiscoveryTests(unittest.TestCase):
    """Under ``.foreman/`` (the worktrees' parent) the live database is not found."""

    def test_a_directory_under_the_runtime_directory_finds_no_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp).resolve() / "repo"
            (main / ".git").mkdir(parents=True)
            (main / ".foreman.db").write_bytes(b"")
            for inside in (main / ".foreman", main / ".foreman" / "worktrees" / "stray"):
                inside.mkdir(parents=True, exist_ok=True)
                self.assertIsNone(discover_repo_local_db_path(inside), inside)
            self.assertEqual(discover_repo_local_db_path(main), main / ".foreman.db")


class CodeAnAgentWroteTests(unittest.TestCase):
    """The tests, the setup command and the agent never get FOREMAN_DB."""

    def test_a_project_cannot_pass_foreman_db_through(self) -> None:
        from foreman.domain.settings import ProjectSettings, SettingsError

        with self.assertRaises(SettingsError):
            ProjectSettings.from_raw({"agent_env_passthrough": ["FOREMAN_DB"]})

    def test_the_database_and_runtime_directory_cannot_be_linked_into_a_worktree(self) -> None:
        from foreman.domain.settings import ProjectSettings, SettingsError

        for entry in (".foreman.db", ".foreman.db-wal", ".foreman/worktrees", ".git"):
            with self.assertRaises(SettingsError, msg=entry):
                ProjectSettings.from_raw({"worktree_link_paths": [entry]})
        ProjectSettings.from_raw({"worktree_link_paths": ["frontend/node_modules"]})

    def test_the_test_command_does_not_get_foreman_db(self) -> None:
        from foreman.engine.builtins import run_tests

        import subprocess

        seen: dict[str, str] = {}

        class Spy(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                if args and args[0][:2] == ["bash", "-lc"]:
                    seen.update(kwargs["env"])
                super().__init__(*args, **kwargs)

        with mock.patch.dict(os.environ, {DB_ENV: "/live/.foreman.db"}), \
                mock.patch.object(run_tests.subprocess, "Popen", Spy):
            with tempfile.TemporaryDirectory() as tmp:
                run_tests.RunTestsStep._run_command(
                    mock.Mock(),
                    command="true",
                    timeout_seconds=30,
                    working_dir=Path(tmp),
                    report_dir=Path(tmp),
                    emit=lambda *_: None,
                    emitted_events=[],
                )
        self.assertTrue(seen, "the test command was not started")
        self.assertNotIn(DB_ENV, seen)


class ReviewDatabaseCopyTests(unittest.TestCase):
    """A review's copy holds this project's rows only, and nothing that is a credential."""

    def test_the_copy_keeps_only_the_project_and_drops_credentials_and_chat(self) -> None:
        from foreman.domain.models import NotificationDestination, Project
        from foreman.engine.agent_step import _keep_only_project

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copy.db"
            with ForemanStore(path) as store:
                store.initialize()
                for pid in ("mine", "theirs"):
                    store.save_project(Project(
                        id=pid, name=pid, repo_path=f"/{pid}", workflow_id="development",
                    ))
                    store.append_meta_turn(project_id=pid, role="user", text=f"secret-{pid}")
                    store.create_api_token(project_id=pid, name="t")
                    store.save_notification_destination(NotificationDestination(
                        id=f"d-{pid}", project_id=pid, name="hook", kind="webhook",
                        target=f"https://hooks.invalid/{pid}",
                    ))
            _keep_only_project(path, "mine")
            with ForemanStore(path) as store:
                rows = store._connection.execute("SELECT id FROM projects").fetchall()
                self.assertEqual([row[0] for row in rows], ["mine"])
                for table in ("meta_turns", "api_tokens", "notification_destinations"):
                    count = store._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    self.assertEqual(count, 0, table)
            # Vacuumed: nothing deleted is left in the file's free pages.
            raw = path.read_bytes()
            self.assertNotIn(b"secret-theirs", raw)
            self.assertNotIn(b"hooks.invalid", raw)

    def test_a_project_that_does_not_ask_gets_no_copy(self) -> None:
        from foreman.domain.settings import ProjectSettings

        self.assertFalse(ProjectSettings.from_raw({}).sandbox_database_copy)
        self.assertTrue(
            ProjectSettings.from_raw({"sandbox_database_copy": True}).sandbox_database_copy
        )


class SessionEnvironmentTests(unittest.TestCase):
    def test_an_agent_never_gets_the_engines_own_claude_session(self) -> None:
        host = {
            "PATH": "/bin",
            "CLAUDE_CONFIG_DIR": "/c",
            "CLAUDECODE": "1",
            "CLAUDE_CODE_MESSAGING_SOCKET": "/run/user/1/cc-socks/1.sock",
            "CLAUDE_CODE_MESSAGING_TOKEN": "t",
            "CLAUDE_CODE_SESSION_ID": "s",
            "CLAUDE_CODE_CHILD_NOTES_DIR": "/n",
            "CLAUDE_CODE_SSE_PORT": "1",
            "CLAUDE_PID": "1",
        }
        env = agent_environment(host=host)
        self.assertEqual(env.get("CLAUDE_CONFIG_DIR"), "/c")
        for name in host:
            if name not in ("PATH", "CLAUDE_CONFIG_DIR"):
                self.assertNotIn(name, env)


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
