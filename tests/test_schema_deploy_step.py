"""Migrations are a deploy step: no repair at open, and a version check at start."""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path

from foreman.api.app import create_dashboard_app
from foreman.cli.engine import handle_dashboard, handle_serve
from foreman.store import ForemanStore, SchemaVersionError
from foreman.store.base import _SCHEMA_MIGRATIONS_DDL, _split_sql_statements
from foreman.store.migrations import MIGRATIONS

LATEST = max(m[0] for m in MIGRATIONS)
DRIFT = [
    ("tasks", "completion_evidence_json"),
    ("tasks", "executor_overrides_json"),
    ("tasks", "task_key"),
    ("tasks", "worktree_path"),
    ("projects", "task_key_prefix"),
]


def _columns(store: ForemanStore, table: str) -> set[str]:
    return {r["name"] for r in store._connection.execute(f"PRAGMA table_info({table})")}


def _without_column(column: str) -> list[tuple[int, str, str]]:
    """The migrations as an old branch's database saw them: no statement names the column."""

    pattern = re.compile(rf"\b{column}\b")
    out = []
    for version, description, sql in MIGRATIONS:
        kept = [st for st in _split_sql_statements(sql) if not pattern.search(st)]
        out.append((version, description, "\n".join(kept) if kept else "SELECT 1;"))
    return out


class DriftMigrationTests(unittest.TestCase):
    def test_each_missing_column_is_added_by_the_migration_only(self) -> None:
        for table, column in DRIFT:
            with self.subTest(column=column), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "f.db"
                with ForemanStore(db) as store:
                    store._connection.executescript(_SCHEMA_MIGRATIONS_DDL)
                    store.migrate(_without_column(column)[: LATEST - 1])
                    self.assertEqual(store.schema_version(), LATEST - 1)
                    self.assertNotIn(column, _columns(store, table))
                with ForemanStore(db) as store:
                    # Opening repairs nothing.
                    self.assertNotIn(column, _columns(store, table))
                    self.assertEqual(store.migrate(), [LATEST])
                    self.assertIn(column, _columns(store, table))

    def test_store_has_no_repair_at_open(self) -> None:
        self.assertFalse(hasattr(ForemanStore, "_repair_known_schema_drift"))


class SchemaCheckTests(unittest.TestCase):
    def _db(self, tmp: str, *, older: bool = False, newer: bool = False) -> str:
        path = str(Path(tmp) / "f.db")
        with ForemanStore(path) as store:
            store._connection.executescript(_SCHEMA_MIGRATIONS_DDL)
            if not older:
                store.initialize()
            if newer:
                store._connection.execute(
                    "INSERT INTO schema_migrations (version, description, applied_at)"
                    " VALUES (?, 'future', 'now')",
                    (LATEST + 1,),
                )
                store._connection.commit()
        return path

    def test_check_schema_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with ForemanStore(self._db(tmp)) as store:
                store.check_schema()
        with tempfile.TemporaryDirectory() as tmp:
            with ForemanStore(self._db(tmp, older=True)) as store:
                with self.assertRaisesRegex(SchemaVersionError, "older.*foreman db migrate"):
                    store.check_schema()
        with tempfile.TemporaryDirectory() as tmp:
            with ForemanStore(self._db(tmp, newer=True)) as store:
                with self.assertRaisesRegex(SchemaVersionError, "newer.*foreman db migrate"):
                    store.check_schema()

    def test_serve_and_dashboard_refuse_both_directions(self) -> None:
        for kind in ({"older": True}, {"newer": True}):
            with tempfile.TemporaryDirectory() as tmp:
                path = self._db(tmp, **kind)
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    serve = handle_serve(
                        argparse.Namespace(db=path, project_id='x', poll_seconds=1.0, once=True)
                    )
                self.assertEqual(serve, 1)
                self.assertIn("foreman db migrate", err.getvalue())
                with self.assertRaises(SchemaVersionError):
                    create_dashboard_app(path)
                self.assertEqual(
                    ForemanStore(path).schema_version(),
                    LATEST + 1 if kind.get("newer") else 0,
                )

    def test_dashboard_command_prints_the_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._db(tmp, older=True)
            args = argparse.Namespace(
                db=path, token=None, token_file=None, host="127.0.0.1", port=0,
                frontend_mode="dist", frontend_dev_url=None, reload=False,
                allowed_origins=[], allow_insecure_network=False, allow_remote_manager=False,
            )
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(handle_dashboard(args), 1)
            self.assertIn("foreman db migrate", err.getvalue())


if __name__ == "__main__":
    unittest.main()
