"""The engine command table: migration 15, the store round-trip, the lock view.

These tests cover the durable control channel on its own — schema shape,
persistence, and the token-free engine lock view. How a resident engine *acts*
on a command lives in ``tests/test_serve.py``; how the CLI queues one lives in
``tests/test_cli.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from foreman.migrations import MIGRATIONS
from foreman.models import (
    ENGINE_COMMAND_STATUSES,
    ENGINE_COMMANDS,
    ENGINE_COMMANDS_NEEDING_A_RESIDENT_ENGINE,
    EngineLockView,
    Project,
    Sprint,
    Task,
)
from foreman.store import ForemanStore

_SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);
"""


def _connection_at_version(version: int) -> sqlite3.Connection:
    """An in-memory database with migrations applied only up to ``version``."""

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_MIGRATIONS_DDL)
    now = datetime.now(timezone.utc).isoformat()
    for number, description, sql in sorted(MIGRATIONS, key=lambda m: m[0]):
        if number > version:
            break
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at)"
            " VALUES (?, ?, ?)",
            (number, description, now),
        )
    conn.commit()
    return conn


def _store_on(conn: sqlite3.Connection) -> ForemanStore:
    store = ForemanStore.__new__(ForemanStore)
    store.db_path = ":memory:"
    store._connection = conn
    store._write_retries = 3
    return store


class Migration15Tests(unittest.TestCase):
    """`engine_commands` must appear at version 15 and only at version 15."""

    def test_a_database_at_version_14_has_no_engine_commands_table(self) -> None:
        conn = _connection_at_version(14)
        self.addCleanup(conn.close)
        self.assertEqual(_store_on(conn).schema_version(), 14)
        self.assertIsNone(
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='engine_commands'"
            ).fetchone()
        )

    def test_migration_15_applies_cleanly_to_a_version_14_database(self) -> None:
        conn = _connection_at_version(14)
        self.addCleanup(conn.close)
        store = _store_on(conn)

        applied = store.migrate()

        self.assertIn(15, applied)
        self.assertEqual(store.schema_version(), 15)
        self.assertIsNotNone(
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='engine_commands'"
            ).fetchone()
        )

    def test_engine_commands_has_the_documented_columns(self) -> None:
        conn = _connection_at_version(15)
        self.addCleanup(conn.close)

        columns = {
            row["name"]: row
            for row in conn.execute("PRAGMA table_info(engine_commands)").fetchall()
        }

        self.assertEqual(
            set(columns),
            {
                "id",
                "project_id",
                "command",
                "task_id",
                "requested_by",
                "requested_at",
                "status",
                "acknowledged_at",
                "completed_at",
                "result_detail",
            },
        )
        for required in ("project_id", "command", "requested_by", "requested_at", "status"):
            self.assertEqual(columns[required]["notnull"], 1, required)
        self.assertEqual(
            columns["task_id"]["notnull"], 0, "task_id must be nullable"
        )

    def test_the_lookup_index_covers_project_status_and_request_time(self) -> None:
        conn = _connection_at_version(15)
        self.addCleanup(conn.close)

        indexes = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='engine_commands'"
            ).fetchall()
        ]
        self.assertIn("idx_engine_commands_project_status", indexes)
        columns = [
            row["name"]
            for row in conn.execute(
                "PRAGMA index_info(idx_engine_commands_project_status)"
            ).fetchall()
        ]
        self.assertEqual(columns, ["project_id", "status", "requested_at"])

    def test_foreign_keys_cascade_from_projects_and_tasks(self) -> None:
        conn = _connection_at_version(15)
        self.addCleanup(conn.close)

        rules = {
            row["table"]: (row["on_delete"], row["from"])
            for row in conn.execute(
                "PRAGMA foreign_key_list(engine_commands)"
            ).fetchall()
        }
        self.assertEqual(rules["projects"], ("CASCADE", "project_id"))
        self.assertEqual(rules["tasks"], ("CASCADE", "task_id"))

    def test_the_command_and_status_vocabularies_are_constrained(self) -> None:
        conn = _connection_at_version(15)
        self.addCleanup(conn.close)
        conn.execute(
            "INSERT INTO projects (id, name, repo_path, workflow_id, created_at, updated_at)"
            " VALUES ('p', 'P', '/tmp/p', 'development', 'now', 'now')"
        )

        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO engine_commands (id, project_id, command, requested_by,"
                " requested_at, status) VALUES ('c1', 'p', 'self_destruct', 'me', 'now', 'pending')"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO engine_commands (id, project_id, command, requested_by,"
                " requested_at, status) VALUES ('c2', 'p', 'pause', 'me', 'now', 'in_flight')"
            )

    def test_the_python_vocabulary_matches_the_schema_constraint(self) -> None:
        """The CHECK constraint and the model tuples must not drift apart."""

        sql = dict((v, s) for v, _d, s in MIGRATIONS)[15]
        for name in ENGINE_COMMANDS:
            self.assertIn(f"'{name}'", sql)
        for status in ENGINE_COMMAND_STATUSES:
            self.assertIn(f"'{status}'", sql)
        for name in ENGINE_COMMANDS_NEEDING_A_RESIDENT_ENGINE:
            self.assertIn(name, ENGINE_COMMANDS)


class EngineCommandStoreTests(unittest.TestCase):
    """`ForemanStore` must round-trip commands and advance their lifecycle."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.store = ForemanStore(Path(self._temp.name) / "foreman.db")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(
            Project(
                id="project-1",
                name="Demo",
                repo_path=self._temp.name,
                workflow_id="development",
            )
        )
        self.store.save_sprint(
            Sprint(id="sprint-1", project_id="project-1", title="S", status="active")
        )
        self.store.save_task(
            Task(
                id="task-1",
                sprint_id="sprint-1",
                project_id="project-1",
                title="Task one",
                status="todo",
            )
        )

    def test_enqueue_round_trips_every_field(self) -> None:
        command = self.store.enqueue_engine_command(
            project_id="project-1",
            command="stop_task",
            requested_by="alice",
            task_id="task-1",
        )

        stored = self.store.get_engine_command(command.id)
        assert stored is not None
        self.assertEqual(stored.project_id, "project-1")
        self.assertEqual(stored.command, "stop_task")
        self.assertEqual(stored.requested_by, "alice")
        self.assertEqual(stored.task_id, "task-1")
        self.assertEqual(stored.status, "pending")
        self.assertTrue(stored.requested_at)
        self.assertIsNone(stored.acknowledged_at)
        self.assertIsNone(stored.completed_at)
        self.assertIsNone(stored.result_detail)

    def test_a_command_without_a_task_is_allowed(self) -> None:
        command = self.store.enqueue_engine_command(
            project_id="project-1", command="pause", requested_by="bob"
        )
        stored = self.store.get_engine_command(command.id)
        assert stored is not None
        self.assertIsNone(stored.task_id)

    def test_an_unknown_command_name_is_refused_before_it_reaches_sqlite(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.store.enqueue_engine_command(
                project_id="project-1", command="explode", requested_by="bob"
            )
        self.assertIn("explode", str(caught.exception))

    def test_next_pending_returns_the_oldest_and_skips_settled_commands(self) -> None:
        first = self.store.enqueue_engine_command(
            project_id="project-1", command="pause", requested_by="a"
        )
        second = self.store.enqueue_engine_command(
            project_id="project-1", command="resume", requested_by="b"
        )

        self.assertEqual(self.store.next_pending_engine_command("project-1").id, first.id)
        self.store.mark_engine_command(first.id, "completed", detail="done")
        self.assertEqual(self.store.next_pending_engine_command("project-1").id, second.id)
        self.store.mark_engine_command(second.id, "rejected", detail="nope")
        self.assertIsNone(self.store.next_pending_engine_command("project-1"))

    def test_next_pending_is_scoped_to_one_project(self) -> None:
        self.store.save_project(
            Project(
                id="project-2",
                name="Other",
                repo_path=self._temp.name,
                workflow_id="development",
            )
        )
        self.store.enqueue_engine_command(
            project_id="project-2", command="pause", requested_by="a"
        )

        self.assertIsNone(self.store.next_pending_engine_command("project-1"))

    def test_marking_acknowledged_then_completed_stamps_both_times(self) -> None:
        command = self.store.enqueue_engine_command(
            project_id="project-1", command="pause", requested_by="a"
        )

        acknowledged = self.store.mark_engine_command(command.id, "acknowledged")
        assert acknowledged is not None
        self.assertEqual(acknowledged.status, "acknowledged")
        self.assertTrue(acknowledged.acknowledged_at)
        self.assertIsNone(acknowledged.completed_at)

        completed = self.store.mark_engine_command(
            command.id, "completed", detail="Engine paused."
        )
        assert completed is not None
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.result_detail, "Engine paused.")
        self.assertTrue(completed.completed_at)
        self.assertEqual(
            completed.acknowledged_at,
            acknowledged.acknowledged_at,
            "completing must not clear the acknowledgement stamp",
        )

    def test_marking_an_unknown_status_is_refused(self) -> None:
        command = self.store.enqueue_engine_command(
            project_id="project-1", command="pause", requested_by="a"
        )
        with self.assertRaises(ValueError):
            self.store.mark_engine_command(command.id, "half_done")

    def test_marking_a_missing_command_returns_none(self) -> None:
        self.assertIsNone(self.store.mark_engine_command("cmd-nope", "completed"))

    def test_list_is_newest_first_and_filterable_by_status(self) -> None:
        old = self.store.enqueue_engine_command(
            project_id="project-1", command="pause", requested_by="a"
        )
        new = self.store.enqueue_engine_command(
            project_id="project-1", command="resume", requested_by="b"
        )
        self.store.mark_engine_command(old.id, "rejected", detail="stale")

        listed = self.store.list_engine_commands("project-1")
        self.assertEqual([c.id for c in listed], [new.id, old.id])

        self.assertEqual(
            [c.id for c in self.store.list_engine_commands("project-1", status="pending")],
            [new.id],
        )
        self.assertEqual(
            [c.id for c in self.store.list_engine_commands("project-1", status="rejected")],
            [old.id],
        )

    def test_list_honours_the_limit(self) -> None:
        for _ in range(5):
            self.store.enqueue_engine_command(
                project_id="project-1", command="pause", requested_by="a"
            )
        self.assertEqual(len(self.store.list_engine_commands("project-1", limit=2)), 2)

    def test_deleting_a_task_cascades_to_its_commands(self) -> None:
        command = self.store.enqueue_engine_command(
            project_id="project-1",
            command="stop_task",
            requested_by="a",
            task_id="task-1",
        )

        self.store.delete_task("task-1")

        self.assertIsNone(self.store.get_engine_command(command.id))


class EngineLockViewTests(unittest.TestCase):
    """`get_engine_lock` must expose who holds a project without the token."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.store = ForemanStore(Path(self._temp.name) / "foreman.db")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(
            Project(
                id="project-1",
                name="Demo",
                repo_path=self._temp.name,
                workflow_id="development",
            )
        )

    def test_no_engine_means_no_view(self) -> None:
        self.assertIsNone(self.store.get_engine_lock("project-1"))

    def test_the_view_reports_the_holder_and_the_lease_window(self) -> None:
        lease = self.store.acquire_lease(
            project_id="project-1",
            resource_type="engine",
            resource_id="project-1",
            holder_id="holder-a",
            lease_token="secret-token",
            duration_seconds=120,
        )
        assert lease is not None

        view = self.store.get_engine_lock("project-1")
        assert view is not None
        self.assertIsInstance(view, EngineLockView)
        self.assertEqual(view.project_id, "project-1")
        self.assertEqual(view.holder_id, "holder-a")
        self.assertEqual(view.acquired_at, lease.acquired_at)
        self.assertEqual(view.heartbeat_at, lease.heartbeat_at)
        self.assertEqual(view.expires_at, lease.expires_at)

    def test_the_view_carries_no_lease_token(self) -> None:
        self.store.acquire_lease(
            project_id="project-1",
            resource_type="engine",
            resource_id="project-1",
            holder_id="holder-a",
            lease_token="secret-token",
        )

        view = self.store.get_engine_lock("project-1")
        assert view is not None
        self.assertNotIn("secret-token", repr(view))
        self.assertFalse(hasattr(view, "lease_token"))

    def test_a_task_lease_is_not_an_engine_lock(self) -> None:
        self.store.acquire_lease(
            project_id="project-1",
            resource_type="task",
            resource_id="task-1",
            holder_id="holder-a",
            lease_token="token",
        )
        self.assertIsNone(self.store.get_engine_lock("project-1"))

    def test_a_released_lock_is_no_longer_reported(self) -> None:
        self.store.acquire_lease(
            project_id="project-1",
            resource_type="engine",
            resource_id="project-1",
            holder_id="holder-a",
            lease_token="token",
        )
        self.store.release_lease(
            project_id="project-1",
            resource_type="engine",
            resource_id="project-1",
            holder_id="holder-a",
            lease_token="token",
        )
        self.assertIsNone(self.store.get_engine_lock("project-1"))

    def test_heartbeat_age_and_expiry_are_computed_from_the_stamps(self) -> None:
        now = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
        view = EngineLockView(
            project_id="project-1",
            holder_id="holder-a",
            acquired_at="2026-09-04T11:55:00Z",
            heartbeat_at="2026-09-04T11:59:30Z",
            expires_at="2026-09-04T12:01:30Z",
        )

        self.assertAlmostEqual(view.heartbeat_age_seconds(now), 30.0)
        self.assertFalse(view.is_expired(now))
        self.assertTrue(view.is_expired(now + timedelta(minutes=5)))

    def test_an_unparseable_stamp_degrades_instead_of_raising(self) -> None:
        view = EngineLockView(
            project_id="project-1",
            holder_id="holder-a",
            acquired_at="whenever",
            heartbeat_at="whenever",
            expires_at="whenever",
        )
        self.assertIsNone(view.heartbeat_age_seconds())
        self.assertFalse(view.is_expired())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
