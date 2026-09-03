"""Regression coverage for the sprint-53 store safety slice.

Covers the Phase 0 defects found by the production-readiness review:
foreign-key failures on retention and deletes, multi-process SQLite sharing
(WAL, busy handling, write retries), atomic migrations, sequence-based task
keys, and validated project settings at every write boundary.
"""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from foreman.dashboard_service import DashboardService, DashboardValidationError
from foreman.migrations import MIGRATIONS
from foreman.models import (
    DecisionGate,
    Event,
    HumanGateDecision,
    MergeWaiver,
    Project,
    Run,
    Sprint,
    Task,
)
from foreman.orchestrator import ForemanOrchestrator, OrchestratorError
from foreman.settings import ProjectSettings, SettingsError
from foreman.store import (
    ForemanStore,
    MigrationError,
    _SCHEMA_MIGRATIONS_DDL,
    _split_sql_statements,
)

_OLD = "2020-01-01T00:00:00.000000Z"
_CUTOFF = "2025-01-01T00:00:00.000000Z"


def _seed(
    store: ForemanStore,
    *,
    project_id: str = "proj-1",
    sprint_id: str = "sprint-1",
    task_id: str = "task-1",
    settings: dict | None = None,
) -> tuple[Project, Sprint, Task]:
    project = Project(
        id=project_id,
        name="Safety Project",
        repo_path="/tmp/safety-project",
        workflow_id="development",
        settings=dict(settings or {}),
        created_at=_OLD,
        updated_at=_OLD,
    )
    store.save_project(project)
    sprint = Sprint(
        id=sprint_id,
        project_id=project_id,
        title="Sprint",
        status="active",
        created_at=_OLD,
        started_at=_OLD,
    )
    store.save_sprint(sprint)
    task = Task(
        id=task_id,
        sprint_id=sprint_id,
        project_id=project_id,
        title="Task",
        status="done",
        created_at=_OLD,
    )
    store.save_task(task)
    return project, sprint, task


def _old_run(store: ForemanStore, task: Task, run_id: str = "run-1") -> Run:
    run = Run(
        id=run_id,
        task_id=task.id,
        project_id=task.project_id,
        role_id="developer",
        workflow_step="develop",
        agent_backend="claude_code",
        status="completed",
        started_at=_OLD,
        completed_at=_OLD,
        created_at=_OLD,
    )
    store.save_run(run)
    store.save_event(
        Event(
            id=f"{run_id}-event",
            run_id=run.id,
            task_id=task.id,
            project_id=task.project_id,
            event_type="agent.message",
            timestamp=_OLD,
        )
    )
    return run


def _decision(store: ForemanStore, task: Task, run: Run | None) -> HumanGateDecision:
    decision = HumanGateDecision(
        id=f"decision-{task.id}",
        task_id=task.id,
        project_id=task.project_id,
        workflow_step="human_approval",
        decision="approve",
        decided_at=_OLD,
        run_id=run.id if run else None,
    )
    store.save_human_gate_decision(decision)
    return decision


def _count(store: ForemanStore, table: str, where: str = "1=1", params: tuple = ()) -> int:
    row = store._connection.execute(
        f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params
    ).fetchone()
    return int(row["n"])


class ConnectionSafetyTests(unittest.TestCase):
    """The engine, dashboard, and CLI share one file; writes must survive that."""

    def test_file_store_uses_wal_and_a_real_busy_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with ForemanStore(Path(tmp) / "safety.db") as store:
                store.initialize()
                journal = store._connection.execute("PRAGMA journal_mode").fetchone()[0]
                busy = store._connection.execute("PRAGMA busy_timeout").fetchone()[0]
                synchronous = store._connection.execute("PRAGMA synchronous").fetchone()[0]
        self.assertEqual(str(journal).lower(), "wal")
        self.assertEqual(int(busy), int(ForemanStore.DEFAULT_BUSY_TIMEOUT_SECONDS * 1000))
        self.assertEqual(int(synchronous), 1)  # NORMAL

    def test_memory_store_skips_wal(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            journal = store._connection.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(str(journal).lower(), "memory")

    def test_hot_writes_retry_while_another_process_holds_the_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "safety.db"
            with ForemanStore(db_path) as seed:
                seed.initialize()
                _, _, task = _seed(seed)
                run = _old_run(seed, task)

            writer = ForemanStore(db_path, busy_timeout_seconds=0.05, write_retries=8)
            blocker = sqlite3.connect(str(db_path), timeout=1.0, check_same_thread=False)
            blocker.execute("BEGIN IMMEDIATE")
            blocker.execute("UPDATE projects SET updated_at = updated_at")

            def release() -> None:
                time.sleep(0.4)
                blocker.commit()

            threading.Thread(target=release, daemon=True).start()
            started = time.monotonic()
            writer.save_event(
                Event(
                    id="late-event",
                    run_id=run.id,
                    task_id=task.id,
                    project_id=task.project_id,
                    event_type="agent.message",
                    timestamp=_OLD,
                )
            )
            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, 0.3)
            self.assertIsNotNone(writer.get_event("late-event"))
            writer.close()
            blocker.close()

    def test_hot_write_fails_clearly_when_retries_are_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "safety.db"
            with ForemanStore(db_path) as seed:
                seed.initialize()
                _, _, task = _seed(seed)
                run = _old_run(seed, task)

            writer = ForemanStore(db_path, busy_timeout_seconds=0.02, write_retries=1)
            blocker = sqlite3.connect(str(db_path), timeout=1.0, check_same_thread=False)
            blocker.execute("BEGIN IMMEDIATE")
            blocker.execute("UPDATE projects SET updated_at = updated_at")
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    writer.save_event(
                        Event(
                            id="never",
                            run_id=run.id,
                            task_id=task.id,
                            project_id=task.project_id,
                            event_type="agent.message",
                            timestamp=_OLD,
                        )
                    )
            finally:
                blocker.rollback()
                blocker.close()
                writer.close()


class TaskKeySequenceTests(unittest.TestCase):
    """Task keys come from a per-project sequence bumped inside the insert."""

    def test_concurrent_writers_never_share_a_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "keys.db"
            with ForemanStore(db_path) as seed:
                seed.initialize()
                _seed(seed, task_id="task-seed")

            writer_count = 8
            barrier = threading.Barrier(writer_count)
            keys: dict[int, str] = {}
            errors: list[BaseException] = []

            def write(index: int) -> None:
                try:
                    with ForemanStore(db_path) as store:
                        barrier.wait(timeout=5)
                        task = Task(
                            id=f"task-{index}",
                            sprint_id="sprint-1",
                            project_id="proj-1",
                            title=f"Task {index}",
                            created_at=_OLD,
                        )
                        store.save_task(task)
                        keys[index] = task.task_key
                except BaseException as exc:  # noqa: BLE001 - surfaced below
                    errors.append(exc)

            threads = [threading.Thread(target=write, args=(i,)) for i in range(writer_count)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)

            self.assertEqual(errors, [])
            self.assertEqual(len(keys), writer_count)
            self.assertEqual(len(set(keys.values())), writer_count)
            with ForemanStore(db_path) as store:
                seq = store._connection.execute(
                    "SELECT task_key_seq FROM projects WHERE id = 'proj-1'"
                ).fetchone()[0]
                self.assertEqual(int(seq), writer_count + 1)  # seed task took the first key
                self.assertEqual(
                    set(keys.values()),
                    {f"SP-{n}" for n in range(2, writer_count + 2)},
                )

    def test_explicit_keys_are_skipped_by_the_sequence(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            _seed(store, task_id="task-seed")  # SP-1
            explicit = Task(
                id="task-explicit",
                sprint_id="sprint-1",
                project_id="proj-1",
                title="Explicit",
                task_key="SP-2",
                created_at=_OLD,
            )
            store.save_task(explicit)
            fresh = Task(
                id="task-fresh",
                sprint_id="sprint-1",
                project_id="proj-1",
                title="Fresh",
                created_at=_OLD,
            )
            store.save_task(fresh)
            self.assertEqual(fresh.task_key, "SP-3")

    def test_duplicate_keys_are_rejected_by_the_schema(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            _seed(store, task_id="task-seed")
            duplicate = Task(
                id="task-dup",
                sprint_id="sprint-1",
                project_id="proj-1",
                title="Dup",
                task_key="SP-1",
                created_at=_OLD,
            )
            with self.assertRaises(sqlite3.IntegrityError):
                store.save_task(duplicate)

    def test_updates_never_reassign_keys(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            _, _, task = _seed(store)
            key = task.task_key
            task.title = "Renamed"
            store.save_task(task)
            self.assertEqual(store.get_task(task.id).task_key, key)
            seq = store._connection.execute(
                "SELECT task_key_seq FROM projects WHERE id = 'proj-1'"
            ).fetchone()[0]
            self.assertEqual(int(seq), 1)


class DependentDeleteTests(unittest.TestCase):
    """Deletes and pruning must honor every table that references a task or run."""

    def test_delete_task_removes_everything_that_references_it(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            _, _, task = _seed(store)
            run = _old_run(store, task)
            _decision(store, task, run)
            store.save_merge_waiver(
                MergeWaiver(
                    id="waiver-1",
                    task_id=task.id,
                    project_id=task.project_id,
                    waiver_type="incomplete_criteria",
                    reason="ok",
                    approved_by="human",
                    branch_name="feat/x",
                    head_sha="abc",
                    base_sha="def",
                )
            )
            self.assertIsNotNone(
                store.acquire_lease(
                    project_id=task.project_id,
                    resource_type="task",
                    resource_id=task.id,
                    holder_id="holder",
                    lease_token="token",
                )
            )

            store.delete_task(task.id)

            self.assertIsNone(store.get_task(task.id))
            for table in ("runs", "events", "human_gate_decisions", "merge_waivers"):
                self.assertEqual(_count(store, table), 0, table)
            self.assertEqual(
                _count(store, "leases", "resource_type = 'task' AND resource_id = ?", (task.id,)),
                0,
            )

    def test_delete_sprint_removes_decision_gates_and_task_dependents(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            _, sprint, task = _seed(store)
            run = _old_run(store, task)
            _decision(store, task, run)
            store.save_decision_gate(
                DecisionGate(
                    id="gate-1",
                    project_id=sprint.project_id,
                    sprint_id=sprint.id,
                    conflict_description="ordering conflict",
                )
            )

            store.delete_sprint(sprint.id)

            self.assertIsNone(store.get_sprint(sprint.id))
            for table in ("tasks", "runs", "events", "human_gate_decisions", "decision_gates"):
                self.assertEqual(_count(store, table), 0, table)

    def test_prune_old_runs_keeps_gate_decisions_and_unlinks_the_run(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            _, _, task = _seed(store)
            run = _old_run(store, task)
            _decision(store, task, run)

            pruned = store.prune_old_runs(project_id=task.project_id, older_than=_CUTOFF)

            self.assertEqual(pruned, 1)
            self.assertIsNone(store.get_run(run.id))
            rows = store._connection.execute(
                "SELECT run_id FROM human_gate_decisions"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0]["run_id"])


class MigrationSafetyTests(unittest.TestCase):
    """Migrations apply atomically and upgrade legacy databases in place."""

    def test_sql_splitter_ignores_semicolons_inside_comments(self) -> None:
        sql = """
        -- first; comment
        CREATE TABLE x (a);

        -- trailing; comment only
        CREATE TABLE y (
            b  -- inline; note
        );
        """
        statements = _split_sql_statements(sql)
        self.assertEqual(len(statements), 2)
        self.assertTrue(statements[0].endswith("CREATE TABLE x (a);"))

    def test_failed_migration_is_rolled_back_atomically(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            latest = max(m[0] for m in MIGRATIONS)
            bad = (
                latest + 1,
                "creates then fails",
                "CREATE TABLE t_partial (a); CREATE TABLE t_partial (a);",
            )
            with self.assertRaises(MigrationError):
                store.migrate([bad])
            tables = {
                row["name"]
                for row in store._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            self.assertNotIn("t_partial", tables)
            self.assertEqual(store.schema_version(), latest)
            self.assertFalse(store._connection.in_transaction)

    def test_migrate_is_a_no_op_when_up_to_date(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            self.assertEqual(store.migrate(), [])

    def test_legacy_v13_database_upgrades_with_decisions_and_unique_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            legacy = ForemanStore(db_path)
            legacy._connection.executescript(_SCHEMA_MIGRATIONS_DDL)
            legacy.migrate(MIGRATIONS[:13])
            self.assertEqual(legacy.schema_version(), 13)
            conn = legacy._connection
            with conn:
                conn.execute(
                    "INSERT INTO projects (id, name, repo_path, workflow_id, created_at,"
                    " updated_at, task_key_prefix) VALUES ('p', 'Safety Project', '/tmp/x',"
                    " 'development', ?, ?, 'SP')",
                    (_OLD, _OLD),
                )
                conn.execute(
                    "INSERT INTO sprints (id, project_id, title, status, created_at)"
                    " VALUES ('s', 'p', 'S', 'active', ?)",
                    (_OLD,),
                )
                for task_id, key in (("t1", "SP-1"), ("t2", "SP-1"), ("t3", "SP-3")):
                    conn.execute(
                        "INSERT INTO tasks (id, sprint_id, project_id, title, status,"
                        " created_at, task_key) VALUES (?, 's', 'p', ?, 'done', ?, ?)",
                        (task_id, task_id, _OLD, key),
                    )
                conn.execute(
                    "INSERT INTO runs (id, task_id, project_id, role_id, workflow_step,"
                    " agent_backend, status, completed_at, created_at) VALUES ('r', 't1', 'p',"
                    " 'developer', 'develop', 'claude_code', 'completed', ?, ?)",
                    (_OLD, _OLD),
                )
                conn.execute(
                    "INSERT INTO human_gate_decisions (id, task_id, project_id, workflow_step,"
                    " decision, decided_at, run_id) VALUES ('d', 't1', 'p', 'gate',"
                    " 'approve', ?, 'r')",
                    (_OLD,),
                )
                conn.execute(
                    "INSERT INTO decision_gates (id, project_id, sprint_id, raised_at,"
                    " conflict_description) VALUES ('g', 'p', 's', ?, 'conflict')",
                    (_OLD,),
                )
            legacy.close()

            with ForemanStore(db_path) as store:
                applied = store.initialize()
                self.assertEqual(applied, [14])

                decision_fks = {
                    row["from"]: row["on_delete"]
                    for row in store._connection.execute(
                        "PRAGMA foreign_key_list(human_gate_decisions)"
                    ).fetchall()
                }
                self.assertEqual(decision_fks["run_id"], "SET NULL")
                self.assertEqual(decision_fks["task_id"], "CASCADE")
                gate_fks = {
                    row["from"]: row["on_delete"]
                    for row in store._connection.execute(
                        "PRAGMA foreign_key_list(decision_gates)"
                    ).fetchall()
                }
                self.assertEqual(gate_fks["sprint_id"], "CASCADE")

                indexes = {
                    row["name"]
                    for row in store._connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index'"
                    ).fetchall()
                }
                self.assertIn("idx_events_task", indexes)
                self.assertIn("idx_tasks_task_key_unique", indexes)

                keys = sorted(
                    row["task_key"]
                    for row in store._connection.execute("SELECT task_key FROM tasks").fetchall()
                )
                self.assertEqual(len(set(keys)), 3)
                self.assertEqual(keys, ["SP-1", "SP-3", "SP-4"])
                seq = store._connection.execute(
                    "SELECT task_key_seq FROM projects WHERE id = 'p'"
                ).fetchone()[0]
                self.assertEqual(int(seq), 4)

                self.assertEqual(_count(store, "human_gate_decisions"), 1)
                self.assertEqual(
                    store.prune_old_runs(project_id="p", older_than=_CUTOFF), 1
                )
                self.assertEqual(_count(store, "human_gate_decisions"), 1)
                store.delete_sprint("s")
                self.assertEqual(_count(store, "decision_gates"), 0)
                self.assertEqual(_count(store, "human_gate_decisions"), 0)


class SettingsValidationTests(unittest.TestCase):
    """Settings are validated once and read through the model everywhere."""

    def test_retention_is_off_unless_configured(self) -> None:
        settings = ProjectSettings.from_raw({})
        self.assertIsNone(settings.event_retention_days)
        self.assertIsNone(settings.run_retention_days)
        self.assertIsNone(settings.prompt_retention_days)
        self.assertEqual(settings.max_infra_retries, 3)
        self.assertEqual(settings.active_run_recovery_timeout_minutes, 0)

    def test_retention_must_be_a_positive_day_count(self) -> None:
        self.assertEqual(ProjectSettings.from_raw({"run_retention_days": 30}).run_retention_days, 30)
        with self.assertRaises(SettingsError):
            ProjectSettings.from_raw({"event_retention_days": 0})
        with self.assertRaises(SettingsError):
            ProjectSettings.from_raw({"prompt_retention_days": "soon"})

    def test_orchestrator_refuses_to_run_a_misconfigured_project(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            project, _, _ = _seed(store, settings={"max_step_visits": "many"})
            orchestrator = ForemanOrchestrator(store)
            with self.assertRaises(OrchestratorError) as raised:
                orchestrator.run_project(project.id)
            self.assertIn("invalid settings", str(raised.exception))

    def test_prune_old_history_reads_validated_retention(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            project, _, task = _seed(store, settings={"run_retention_days": 1})
            _old_run(store, task)
            orchestrator = ForemanOrchestrator(store)
            counts = orchestrator.prune_old_history(project)
            self.assertEqual(counts.get("runs"), 1)
            self.assertNotIn("events", counts)

    def test_dashboard_rejects_invalid_settings_and_keeps_the_old_ones(self) -> None:
        with ForemanStore(":memory:") as store:
            store.initialize()
            project, _, _ = _seed(store, settings={"max_step_visits": 4})
            service = DashboardService(store)
            with self.assertRaises(DashboardValidationError):
                service.update_project_settings(
                    project.id, updates={"settings": {"max_step_visits": -1}}
                )
            self.assertEqual(store.get_project(project.id).settings["max_step_visits"], 4)
            service.update_project_settings(
                project.id, updates={"settings": {"run_retention_days": 14}}
            )
            self.assertEqual(store.get_project(project.id).settings["run_retention_days"], 14)


if __name__ == "__main__":
    unittest.main()
