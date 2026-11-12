"""Tests for the Foreman schema migration framework."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from foreman.migrations import MIGRATIONS
from foreman.models import (
    PROPOSAL_STATES,
    Proposal,
    AUTONOMY_LEVELS,
    RUN_STATUSES,
    SPRINT_STATUSES,
    TASK_COMPLEXITIES,
    TASK_STATUSES,
    TASK_TYPES,
    Project,
    Run,
    Sprint,
    Task,
)
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


class SchemaRepairTests(unittest.TestCase):
    """Repair known local schema drift during initialize()."""

    def test_initialize_repairs_missing_completion_evidence_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "foreman.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                conn.executescript(_SCHEMA_MIGRATIONS_DDL)

                # Simulate a long-lived local DB whose ledger says version 5
                # is present even though the tasks table still has the pre-
                # completion-evidence shape.
                for version, description, sql in MIGRATIONS[:4]:
                    conn.executescript(sql)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, description, applied_at)"
                        " VALUES (?, ?, datetime('now'))",
                        (version, description),
                    )
                conn.execute(
                    "INSERT INTO schema_migrations (version, description, applied_at)"
                    " VALUES (5, 'stale local migration ledger entry', datetime('now'))"
                )
                conn.commit()

                before = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
                }
                self.assertNotIn("completion_evidence_json", before)
            finally:
                conn.close()

            with ForemanStore(db_path) as store:
                store.initialize()
                after = {
                    row["name"]
                    for row in store._connection.execute("PRAGMA table_info(tasks)").fetchall()
                }
                self.assertIn("completion_evidence_json", after)


class MetaAgentPersistenceMigrationTests(unittest.TestCase):
    """Migration 11 must create the meta-agent persistence tables."""

    def test_fresh_db_has_meta_tables(self) -> None:
        with _make_store() as store:
            tables = {
                row["name"]
                for row in store._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("meta_sessions", tables)
            self.assertIn("meta_turns", tables)

    def test_existing_db_upgraded_adds_meta_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "foreman.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.row_factory = sqlite3.Row
                conn.executescript(_SCHEMA_MIGRATIONS_DDL)
                # Apply only the migrations before 11 to model an older DB that
                # predates meta-agent persistence.
                for version, description, sql in MIGRATIONS:
                    if version >= 11:
                        continue
                    conn.executescript(sql)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, description, applied_at)"
                        " VALUES (?, ?, datetime('now'))",
                        (version, description),
                    )
                conn.commit()
                before = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                self.assertNotIn("meta_turns", before)
            finally:
                conn.close()

            with ForemanStore(db_path) as store:
                store.initialize()
                self.assertEqual(store.schema_version(), len(MIGRATIONS))
                tables = {
                    row["name"]
                    for row in store._connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                self.assertIn("meta_sessions", tables)
                self.assertIn("meta_turns", tables)


class VocabularyGuardTests(unittest.TestCase):
    """Migration 20: the database refuses statuses and types Foreman lacks."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.store = ForemanStore(Path(self._temp.name) / "foreman.db")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(
            Project(id="p1", name="P", repo_path=self._temp.name, workflow_id="development")
        )
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        self.store.save_task(Task(id="t1", sprint_id="s1", project_id="p1", title="T"))

    def _execute(self, sql: str, params: tuple = ()) -> None:
        connection = self.store._connection
        try:
            connection.execute(sql, params)
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def test_an_unknown_task_status_is_refused_on_update_and_insert(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError) as caught:
            self._execute("UPDATE tasks SET status = 'finished' WHERE id = 't1'")
        self.assertIn("invalid tasks.status", str(caught.exception))

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_task(
                Task(id="t2", sprint_id="s1", project_id="p1", title="T", status="doing")  # type: ignore[arg-type]
            )
        self.assertIsNone(self.store.get_task("t2"))
        self.assertEqual(self.store.get_task("t1").status, "todo")

    def test_unknown_task_type_sprint_status_run_status_and_autonomy_are_refused(self) -> None:
        cases = (
            ("UPDATE tasks SET task_type = 'bug' WHERE id = 't1'", "tasks.task_type"),
            ("UPDATE tasks SET complexity = 'huge' WHERE id = 't1'", "tasks.complexity"),
            ("UPDATE sprints SET status = 'done' WHERE id = 's1'", "sprints.status"),
            ("UPDATE projects SET autonomy_level = 'full' WHERE id = 'p1'", "projects.autonomy_level"),
        )
        for sql, column in cases:
            with self.subTest(column=column):
                with self.assertRaises(sqlite3.IntegrityError) as caught:
                    self._execute(sql)
                self.assertIn(f"invalid {column}", str(caught.exception))

        with self.assertRaises(sqlite3.IntegrityError) as caught:
            self.store.save_run(
                Run(
                    id="r1",
                    task_id="t1",
                    project_id="p1",
                    role_id="developer",
                    workflow_step="develop",
                    agent_backend="claude_code",
                    status="blocked",  # type: ignore[arg-type]
                )
            )
        self.assertIn("invalid runs.status", str(caught.exception))

    def test_every_value_in_the_models_vocabulary_is_accepted(self) -> None:
        for status in TASK_STATUSES:
            self._execute("UPDATE tasks SET status = ? WHERE id = 't1'", (status,))
        for task_type in TASK_TYPES:
            self._execute("UPDATE tasks SET task_type = ? WHERE id = 't1'", (task_type,))
        for complexity in (*TASK_COMPLEXITIES, None):
            self._execute("UPDATE tasks SET complexity = ? WHERE id = 't1'", (complexity,))
        for status in SPRINT_STATUSES:
            self._execute("UPDATE sprints SET status = ? WHERE id = 's1'", (status,))
        for level in AUTONOMY_LEVELS:
            self._execute("UPDATE projects SET autonomy_level = ? WHERE id = 'p1'", (level,))
        self.store.save_run(
            Run(
                id="r1",
                task_id="t1",
                project_id="p1",
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
            )
        )
        for status in RUN_STATUSES:
            self._execute("UPDATE runs SET status = ? WHERE id = 'r1'", (status,))

    def test_a_row_that_already_holds_an_unknown_value_can_still_be_changed(self) -> None:
        connection = self.store._connection
        connection.execute("DROP TRIGGER tasks_status_update_guard")
        connection.execute("UPDATE tasks SET status = 'legacy' WHERE id = 't1'")
        connection.commit()
        self.store.close()
        self.store = ForemanStore(Path(self._temp.name) / "foreman.db")
        self.addCleanup(self.store.close)
        # Other columns of the row stay writable, and the status can be fixed.
        self._execute("UPDATE tasks SET title = 'renamed' WHERE id = 't1'")
        self._execute("UPDATE tasks SET status = 'todo' WHERE id = 't1'")
        self.assertEqual(self.store.get_task("t1").title, "renamed")


class BacklogMigrationTests(unittest.TestCase):
    """Migration 21: intake queues become backlogs (ADR-0021)."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        connection = sqlite3.connect(self.db_path)
        connection.executescript(_SCHEMA_MIGRATIONS_DDL)
        for version, description, sql in MIGRATIONS:
            if version > 20:
                break
            connection.executescript(sql)
            connection.execute(
                "INSERT INTO schema_migrations (version, description, applied_at)"
                " VALUES (?, ?, '2026-11-01T00:00:00Z')",
                (version, description),
            )
        now = "2026-11-01T00:00:00Z"
        for project_id in ("p1", "p2", "p3", "p4"):
            connection.execute(
                "INSERT INTO projects (id, name, repo_path, workflow_id, created_at, updated_at)"
                " VALUES (?, ?, '/tmp', 'development', ?, ?)",
                (project_id, project_id.upper(), now, now),
            )

        def sprint(sprint_id: str, project_id: str, status: str, title: str = "Intake queue") -> None:
            connection.execute(
                "INSERT INTO sprints (id, project_id, title, status, created_at, started_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (sprint_id, project_id, title, status, now, now if status == "active" else None),
            )

        def task(task_id: str, sprint_id: str, project_id: str, status: str) -> None:
            connection.execute(
                "INSERT INTO tasks (id, sprint_id, project_id, title, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, sprint_id, project_id, task_id, status, now),
            )

        # p1: a planned queue of waiting work, and a cancelled task.
        sprint("p1-intake", "p1", "planned")
        task("p1-filed", "p1-intake", "p1", "triage")
        task("p1-accepted", "p1-intake", "p1", "todo")
        task("p1-cancelled", "p1-intake", "p1", "cancelled")
        # p2: a queue the engine was running, with work in flight.
        sprint("p2-intake", "p2", "active")
        task("p2-filed", "p2-intake", "p2", "triage")
        task("p2-running", "p2-intake", "p2", "in_progress")
        task("p2-done", "p2-intake", "p2", "done")
        # p3: a queue holding only waiting work; it is emptied and removed.
        sprint("p3-intake", "p3", "planned")
        task("p3-filed", "p3-intake", "p3", "triage")
        # p4: no intake queue at all, and an ordinary sprint.
        sprint("s4", "p4", "active", title="Sprint 4")
        task("p4-task", "s4", "p4", "todo")
        connection.commit()
        connection.close()

        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.applied = self.store.initialize()

    def sprint_of(self, task_id: str) -> Sprint:
        task = self.store.get_task(task_id)
        assert task is not None
        sprint = self.store.get_sprint(task.sprint_id)
        assert sprint is not None
        return sprint

    def test_the_schema_version_is_bumped_once(self) -> None:
        self.assertEqual(self.applied, [version for version, _, _ in MIGRATIONS if version >= 21])
        self.assertEqual(self.store.schema_version(), MIGRATIONS[-1][0])

    def test_waiting_intake_work_is_in_the_backlog(self) -> None:
        for task_id, status in (("p1-filed", "triage"), ("p1-accepted", "todo"), ("p2-filed", "triage")):
            with self.subTest(task=task_id):
                sprint = self.sprint_of(task_id)
                self.assertEqual((sprint.kind, sprint.status), ("backlog", "planned"))
                self.assertEqual(sprint.id, f"{task_id[:2]}-backlog")
                self.assertEqual(self.store.get_task(task_id).status, status)
        self.assertEqual(self.store.get_backlog("p1").title, "Backlog")

    def test_started_and_finished_work_keeps_its_sprint(self) -> None:
        self.assertEqual(self.store.get_task("p1-cancelled").sprint_id, "p1-intake")
        self.assertEqual(self.store.get_task("p2-running").sprint_id, "p2-intake")
        self.assertEqual(self.store.get_task("p2-done").sprint_id, "p2-intake")
        # The running queue keeps running; the one left with only finished work is finished.
        self.assertEqual(self.store.get_sprint("p2-intake").status, "active")
        p1_queue = self.store.get_sprint("p1-intake")
        self.assertEqual(p1_queue.status, "completed")
        self.assertIsNotNone(p1_queue.completed_at)

    def test_an_emptied_queue_is_removed_and_projects_without_one_get_no_backlog(self) -> None:
        self.assertIsNone(self.store.get_sprint("p3-intake"))
        self.assertEqual(self.sprint_of("p3-filed").id, "p3-backlog")
        self.assertIsNone(self.store.get_backlog("p4"))
        self.assertEqual(self.store.get_task("p4-task").sprint_id, "s4")

    def test_the_backlog_is_not_listed_or_run_as_a_sprint(self) -> None:
        self.assertEqual([s.id for s in self.store.list_sprints("p3")], [])
        self.assertIsNone(self.store.get_active_sprint("p3"))
        self.assertIsNone(self.store.get_next_planned_sprint("p3"))
        self.assertEqual(self.store.get_active_sprint("p2").id, "p2-intake")

    def test_replaying_the_migration_changes_nothing(self) -> None:
        connection = self.store._connection
        before = connection.execute("SELECT id, sprint_id FROM tasks ORDER BY id").fetchall()
        sql = next(entry[2] for entry in MIGRATIONS if entry[0] == 21)
        replay = sql[sql.index("INSERT INTO sprints"):]
        connection.executescript(replay)
        after = connection.execute("SELECT id, sprint_id FROM tasks ORDER BY id").fetchall()
        self.assertEqual([tuple(r) for r in before], [tuple(r) for r in after])
        self.assertEqual(
            connection.execute("SELECT COUNT(*) FROM sprints WHERE kind = 'backlog'").fetchone()[0], 3
        )

    def test_the_database_keeps_a_backlog_planned_and_one_per_project(self) -> None:
        backlog = self.store.get_backlog("p1")
        for status in ("active", "completed", "cancelled"):
            with self.subTest(status=status), self.assertRaises(sqlite3.IntegrityError):
                with self.store._connection:
                    self.store._connection.execute(
                        "UPDATE sprints SET status = ? WHERE id = ?", (status, backlog.id)
                    )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_sprint(
                Sprint(id="p1-second", project_id="p1", title="B", kind="backlog")
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_sprint(Sprint(id="odd", project_id="p1", title="O", kind="pile"))  # type: ignore[arg-type]
        self.assertEqual(self.store.ensure_backlog("p1", created_at="x").id, backlog.id)

    def test_declined_is_a_task_status_the_database_accepts(self) -> None:
        with self.store._connection:
            self.store._connection.execute("UPDATE tasks SET status = 'declined' WHERE id = 'p1-filed'")
        self.assertEqual(self.store.get_task("p1-filed").status, "declined")


if __name__ == "__main__":
    unittest.main()


class ProposalMigrationTests(unittest.TestCase):
    """Migration 22: proposals, the changes the manager proposes (ADR-0022)."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        store = ForemanStore(self.db_path)
        store._connection.executescript(_SCHEMA_MIGRATIONS_DDL)
        store.migrate([m for m in MIGRATIONS if m[0] <= 21])
        store.save_project(Project(id="p1", name="P", repo_path="/tmp", workflow_id="development"))
        store.close()
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)

    def test_an_existing_database_gains_the_table_and_keeps_its_rows(self) -> None:
        self.assertEqual(self.store.schema_version(), 21)
        self.assertEqual(self.store.initialize(), [22])
        self.assertEqual(MIGRATIONS[-1][0], 22)
        self.assertIsNotNone(self.store.get_project("p1"))
        columns = {
            row["name"]
            for row in self.store._connection.execute("PRAGMA table_info(proposals)").fetchall()
        }
        self.assertEqual(
            columns,
            {
                "id", "project_id", "proposed_by", "session_id", "turn_id", "reason",
                "operations_json", "leaves_json", "names_json", "state", "created_at",
                "decided_by", "decided_at", "outcome_json",
            },
        )
        self.assertEqual(self.store.initialize(), [])

    def test_a_proposal_round_trips_and_its_state_is_guarded(self) -> None:
        self.store.initialize()
        proposal = Proposal(
            id="prop-1",
            project_id="p1",
            proposed_by="manager",
            reason="Why.",
            operations=[{"kind": "create_sprint", "title": "S"}],
            names={"tasks": {}, "sprints": {}},
        )
        self.store.save_proposal(proposal)
        self.assertEqual(self.store.get_proposal("prop-1"), proposal)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store._connection:
                self.store._connection.execute(
                    "UPDATE proposals SET state = 'maybe' WHERE id = 'prop-1'"
                )
        for state in PROPOSAL_STATES:
            proposal.state = state
            self.store.save_proposal(proposal)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_proposal(Proposal(id="prop-2", project_id="nope", proposed_by="x", reason="r", operations=[]))

