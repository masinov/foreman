"""Tests for the Foreman schema migration framework."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from foreman.migrations import MIGRATIONS
from foreman.store import ForemanStore, _SCHEMA_MIGRATIONS_DDL


def _make_store(db_path: str | Path = ":memory:") -> ForemanStore:
    store = ForemanStore(db_path)
    store.initialize()
    return store


class MigrationListIntegrityTests(unittest.TestCase):
    """Verify the MIGRATIONS list is internally consistent."""

    def test_migrations_list_is_non_empty(self) -> None:
        self.assertGreater(len(MIGRATIONS), 0)

    def test_versions_are_consecutive_from_one(self) -> None:
        versions = [m[0] for m in sorted(MIGRATIONS, key=lambda m: m[0])]
        self.assertEqual(versions, list(range(1, len(MIGRATIONS) + 1)))

    def test_all_entries_have_non_empty_description_and_sql(self) -> None:
        for version, description, sql in MIGRATIONS:
            self.assertTrue(description.strip(), f"migration {version} has empty description")
            self.assertTrue(sql.strip(), f"migration {version} has empty sql")


class FreshInstallTests(unittest.TestCase):
    """A brand-new database must reach the latest schema version after initialize()."""

    def test_fresh_db_reaches_latest_version(self) -> None:
        with _make_store() as store:
            expected = max(m[0] for m in MIGRATIONS)
            self.assertEqual(store.schema_version(), expected)

    def test_fresh_db_schema_migrations_table_exists(self) -> None:
        with _make_store() as store:
            row = store._connection.execute(
                "SELECT COUNT(*) AS n FROM schema_migrations"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row["n"]), len(MIGRATIONS))

    def test_fresh_db_all_baseline_tables_exist(self) -> None:
        expected_tables = {"projects", "sprints", "tasks", "runs", "events"}
        with _make_store() as store:
            rows = store._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            actual = {row["name"] for row in rows}
            self.assertTrue(
                expected_tables.issubset(actual),
                f"missing tables: {expected_tables - actual}",
            )

    def test_fresh_db_all_baseline_indexes_exist(self) -> None:
        expected_indexes = {
            "idx_tasks_project",
            "idx_tasks_sprint",
            "idx_runs_task",
            "idx_runs_project",
            "idx_events_run",
            "idx_events_project",
            "idx_events_type",
            "idx_sprints_active_project",
        }
        with _make_store() as store:
            rows = store._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
            actual = {row["name"] for row in rows}
            self.assertTrue(
                expected_indexes.issubset(actual),
                f"missing indexes: {expected_indexes - actual}",
            )


class IdempotencyTests(unittest.TestCase):
    """initialize() and migrate() called multiple times must not raise or duplicate records."""

    def test_initialize_twice_is_idempotent(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            version_after_first = store.schema_version()
            store.initialize()
            version_after_second = store.schema_version()
            self.assertEqual(version_after_first, version_after_second)

    def test_migrate_on_up_to_date_db_returns_empty_list(self) -> None:
        with _make_store() as store:
            applied = store.migrate()
            self.assertEqual(applied, [])

    def test_schema_migrations_rows_not_duplicated_on_second_initialize(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            store.initialize()
            row = store._connection.execute(
                "SELECT COUNT(*) AS n FROM schema_migrations"
            ).fetchone()
            self.assertEqual(int(row["n"]), len(MIGRATIONS))

    def test_initialize_is_idempotent_on_file_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "foreman.db"
            with ForemanStore(db_path) as store:
                store.initialize()
                v1 = store.schema_version()
            with ForemanStore(db_path) as store:
                store.initialize()
                v2 = store.schema_version()
            self.assertEqual(v1, v2)


class IncrementalUpgradeTests(unittest.TestCase):
    """A database that only has older migrations applied must be upgraded correctly."""

    def _apply_migrations_up_to(self, version: int) -> ForemanStore:
        """Return an open store with migrations applied only up to `version`."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        # Bootstrap the tracking table manually.
        conn.executescript(_SCHEMA_MIGRATIONS_DDL)

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        for v, desc, sql in sorted(MIGRATIONS, key=lambda m: m[0]):
            if v > version:
                break
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, description, applied_at)"
                " VALUES (?, ?, ?)",
                (v, desc, now),
            )
        conn.commit()

        # Hand the connection over to a ForemanStore without calling initialize().
        store = ForemanStore.__new__(ForemanStore)
        store.db_path = ":memory:"
        store._connection = conn
        return store

    def test_schema_version_zero_before_any_migration(self) -> None:
        store = ForemanStore.__new__(ForemanStore)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA_MIGRATIONS_DDL)
        store.db_path = ":memory:"
        store._connection = conn
        try:
            self.assertEqual(store.schema_version(), 0)
        finally:
            conn.close()

    def test_migrate_returns_applied_version_numbers(self) -> None:
        # Apply only up to version 0 (empty tracking table, no schema yet).
        store = ForemanStore.__new__(ForemanStore)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA_MIGRATIONS_DDL)
        store.db_path = ":memory:"
        store._connection = conn
        try:
            applied = store.migrate()
            self.assertEqual(applied, [m[0] for m in sorted(MIGRATIONS, key=lambda m: m[0])])
        finally:
            conn.close()

    def test_partial_db_upgraded_to_latest(self) -> None:
        """If there are N > 1 migrations, a DB at version N-1 is upgraded to N."""
        if len(MIGRATIONS) < 2:
            self.skipTest("need at least 2 migrations to test incremental upgrade")

        second_last = sorted(MIGRATIONS, key=lambda m: m[0])[-2][0]
        store = self._apply_migrations_up_to(second_last)
        try:
            self.assertEqual(store.schema_version(), second_last)
            applied = store.migrate()
            latest = max(m[0] for m in MIGRATIONS)
            self.assertIn(latest, applied)
            self.assertEqual(store.schema_version(), latest)
        finally:
            store._connection.close()


class SchemaVersionTests(unittest.TestCase):
    """schema_version() must accurately reflect the highest applied migration."""

    def test_schema_version_equals_max_migration_version_after_fresh_install(self) -> None:
        with _make_store() as store:
            expected = max(m[0] for m in MIGRATIONS)
            self.assertEqual(store.schema_version(), expected)

    def test_schema_version_recorded_in_schema_migrations_table(self) -> None:
        with _make_store() as store:
            v = store.schema_version()
            row = store._connection.execute(
                "SELECT version FROM schema_migrations WHERE version = ?", (v,)
            ).fetchone()
            self.assertIsNotNone(row)

    def test_applied_at_column_is_iso8601(self) -> None:
        with _make_store() as store:
            rows = store._connection.execute(
                "SELECT applied_at FROM schema_migrations"
            ).fetchall()
            self.assertGreater(len(rows), 0)
            for row in rows:
                applied_at = row["applied_at"]
                self.assertIn("T", applied_at, f"applied_at not ISO 8601: {applied_at!r}")


if __name__ == "__main__":
    unittest.main()
