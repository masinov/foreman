"""The connection, the write helper and the schema: what every store part shares."""

from __future__ import annotations

import functools
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence, TypeVar

from ..errors import ForemanError
from ..migrations import MIGRATIONS

#: Lease resource type for the per-project engine lock. Defined here rather
#: than imported from ``foreman.engine_lock`` because that module imports the
#: store; the string is the schema-level contract both sides agree on.
ENGINE_RESOURCE_TYPE = "engine"


_PRUNE_PROTECTED_TASK_STATUSES = ("blocked", "in_progress")


_T = TypeVar("_T")
_S = TypeVar("_S", bound="StoreBase")


class MigrationError(ForemanError):
    """Raised when a schema migration fails; the database is left unchanged."""


def _split_sql_statements(sql: str) -> list[str]:
    """Split a migration script into individual statements.

    Uses ``sqlite3.complete_statement`` so semicolons inside comments or string
    literals do not split a statement. Chunks that contain only comments and
    whitespace are dropped.
    """

    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        buffer.append(line)
        candidate = "\n".join(buffer)
        if sqlite3.complete_statement(candidate):
            if _has_sql_content(candidate):
                statements.append(candidate.strip())
            buffer = []
    leftover = "\n".join(buffer)
    if _has_sql_content(leftover):
        statements.append(leftover.strip())
    return statements


def _has_sql_content(chunk: str) -> bool:
    for line in chunk.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return True
    return False


def _is_locked_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message


_SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);
"""


def _retry_when_locked(attempt_write: Callable[[], _T], retries: int) -> _T:
    """Call ``attempt_write``, replaying it when another process holds the lock."""

    attempt = 0
    while True:
        try:
            return attempt_write()
        except sqlite3.OperationalError as exc:
            if not _is_locked_error(exc) or attempt >= retries:
                raise
            attempt += 1
            time.sleep(min(0.05 * (2**attempt), 1.0))


def retried_on_lock(method: Callable[..., _T]) -> Callable[..., _T]:
    """Give a store method that writes the same lock handling as ``_write``.

    For methods that open their own ``with self._connection`` transaction
    (they read, decide and write inside it). The whole method is replayed
    after a lock error, so it must hold exactly one transaction and compute
    anything it needs afresh on each call.
    """

    @functools.wraps(method)
    def wrapper(self: "StoreBase", *args: Any, **kwargs: Any) -> _T:
        return _retry_when_locked(lambda: method(self, *args, **kwargs), self._write_retries)

    return wrapper


class _Connection:
    """The store's SQLite connection, able to hold one transaction open.

    Store methods write inside ``with self._connection:``, which commits when
    the block ends. Outside ``StoreBase.atomic`` that is what happens. Inside
    it, those blocks join the open transaction instead: nothing commits until
    ``atomic`` does, and an error anywhere rolls all of it back. Everything
    else is the ``sqlite3.Connection``.
    """

    __slots__ = ("_raw", "_atomic")

    def __init__(self, raw: sqlite3.Connection) -> None:
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_atomic", False)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._raw, name, value)

    def __enter__(self) -> sqlite3.Connection:
        if self._atomic:
            return self._raw
        return self._raw.__enter__()

    def __exit__(self, *exc_info: object) -> bool:
        if self._atomic:
            # The enclosing atomic block commits or rolls back.
            return False
        return bool(self._raw.__exit__(*exc_info))


class StoreBase:
    """One SQLite connection, with safe writes and schema migrations."""

    #: Default wait for a busy database before a write attempt fails.
    DEFAULT_BUSY_TIMEOUT_SECONDS = 30.0
    #: Retries for hot writes after the busy timeout expires.
    DEFAULT_WRITE_RETRIES = 5
    _PRUNE_TERMINAL_RUN_STATUSES: tuple[str, ...] = (
        "completed",
        "failed",
        "killed",
        "timeout",
    )

    def __init__(
        self,
        db_path: str | Path,
        *,
        busy_timeout_seconds: float = DEFAULT_BUSY_TIMEOUT_SECONDS,
        write_retries: int = DEFAULT_WRITE_RETRIES,
    ) -> None:
        if str(db_path) == ":memory:":
            self.db_path = ":memory:"
        else:
            path = Path(db_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(path)
        self._busy_timeout_seconds = float(busy_timeout_seconds)
        self._write_retries = max(0, int(write_retries))
        self._connection: Any = _Connection(
            sqlite3.connect(self.db_path, timeout=self._busy_timeout_seconds)
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        if self.db_path != ":memory:":
            self._configure_file_database()

    def _configure_file_database(self) -> None:
        """Configure a file-backed database for multi-process sharing.

        The engine, the dashboard, and the CLI all open the same file. WAL mode
        lets readers proceed while a writer commits, and ``synchronous=NORMAL``
        keeps WAL durable across process crashes without an fsync per commit.
        Failures (read-only media, unsupported filesystems) fall back to the
        default journal silently; correctness does not depend on WAL.
        """

        try:
            self._connection.execute("PRAGMA journal_mode = WAL").fetchone()
            self._connection.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.OperationalError:
            pass

    def _write(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        """Run one write transaction, retrying when another process holds the lock.

        ``operation`` runs inside ``with self._connection`` so it commits on
        success and rolls back on any exception. A lock error after the busy
        timeout is retried with a short backoff; the whole operation is
        replayed, so callers must not rely on side effects from a failed
        attempt.
        """

        def transaction() -> _T:
            with self._connection:
                return operation(self._connection)

        return _retry_when_locked(transaction, self._write_retries)

    @contextmanager
    def atomic(self, *, commit: bool = True) -> Iterator[None]:
        """Hold one write transaction open across several store calls.

        Every store write inside the block joins one ``BEGIN IMMEDIATE``
        transaction, so the block commits whole or not at all. An exception
        rolls it back and propagates. With ``commit=False`` it is always
        rolled back: a dry run that sees its own writes and leaves nothing.
        Blocks do not nest.
        """

        connection = self._connection
        if connection._atomic:
            raise RuntimeError("atomic() blocks do not nest.")
        if connection.in_transaction:
            connection.commit()
        _retry_when_locked(lambda: connection.execute("BEGIN IMMEDIATE"), self._write_retries)
        object.__setattr__(connection, "_atomic", True)
        try:
            yield
        except BaseException:
            connection.rollback()
            raise
        else:
            if commit:
                connection.commit()
            else:
                connection.rollback()
        finally:
            object.__setattr__(connection, "_atomic", False)

    def __enter__(self: _S) -> _S:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self._connection.close()

    def initialize(self) -> list[int]:
        """Create or upgrade the schema to the latest migration version.

        Returns the list of migration version numbers applied in this call.
        An already up-to-date database returns an empty list.
        """

        with self._connection:
            self._connection.executescript(_SCHEMA_MIGRATIONS_DDL)
        applied = self.migrate()
        self._repair_known_schema_drift()
        self._backfill_task_keys()
        return applied

    def schema_version(self) -> int:
        """Return the highest migration version applied to this database, or 0."""

        row = self._connection.execute(
            "SELECT MAX(version) AS v FROM schema_migrations"
        ).fetchone()
        if row is None or row["v"] is None:
            return 0
        return int(row["v"])

    def data_version(self) -> int:
        """Return SQLite's ``PRAGMA data_version`` for this connection.

        The value changes whenever *another* connection commits to the
        database. A reader holding its own connection (a stream or watch loop)
        can poll this cheaply and skip its expensive query when nothing has
        changed since the last tick.
        """

        row = self._connection.execute("PRAGMA data_version").fetchone()
        if row is None:
            return 0
        return int(row[0])

    def migrate(
        self,
        migrations: Sequence[tuple[int, str, str]] | None = None,
    ) -> list[int]:
        """Apply all unapplied migrations in version order.

        Each migration's statements and its ledger row are applied inside one
        ``BEGIN IMMEDIATE`` transaction: a failure rolls the whole migration
        back and raises ``MigrationError``. The ledger is re-checked inside
        the transaction so two processes migrating concurrently cannot apply
        the same version twice.

        Returns the list of version numbers that were applied in this call.
        Calling migrate() on an up-to-date database is a no-op that returns an
        empty list.
        """

        entries = sorted(MIGRATIONS if migrations is None else migrations, key=lambda m: m[0])
        current = self.schema_version()
        applied: list[int] = []
        now = datetime.now(timezone.utc).isoformat()
        connection = self._connection

        for version, description, sql in entries:
            if version <= current:
                continue
            if connection.in_transaction:
                connection.commit()
            connection.execute("BEGIN IMMEDIATE")
            try:
                already = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?",
                    (version,),
                ).fetchone()
                if already is not None:
                    connection.rollback()
                    continue
                for statement in _split_sql_statements(sql):
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations (version, description, applied_at)"
                    " VALUES (?, ?, ?)",
                    (version, description, now),
                )
                connection.commit()
            except Exception as exc:
                connection.rollback()
                raise MigrationError(
                    f"Migration {version} ({description}) failed and was rolled back: {exc}"
                ) from exc
            applied.append(version)

        return applied

    def _repair_known_schema_drift(self) -> None:
        """Repair additive schema drift that can occur in long-lived local DBs.

        This is intentionally narrow. It handles cases where a local database
        has migration ledger state that does not match the actual table shape,
        which can happen when experimental branches reuse or reshuffle
        migration versions before landing on main.
        """

        task_columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "completion_evidence_json" not in task_columns:
            with self._connection:
                self._connection.execute(
                    "ALTER TABLE tasks ADD COLUMN completion_evidence_json TEXT NOT NULL DEFAULT ''"
                )
        if "executor_overrides_json" not in task_columns:
            with self._connection:
                self._connection.execute(
                    "ALTER TABLE tasks ADD COLUMN executor_overrides_json TEXT NOT NULL DEFAULT '{}'"
                )
        if "complexity" not in task_columns:
            with self._connection:
                self._connection.execute(
                    "ALTER TABLE tasks ADD COLUMN complexity TEXT"
                )
        if "task_key" not in task_columns:
            with self._connection:
                self._connection.execute(
                    "ALTER TABLE tasks ADD COLUMN task_key TEXT NOT NULL DEFAULT ''"
                )
        if "worktree_path" not in task_columns:
            with self._connection:
                self._connection.execute(
                    "ALTER TABLE tasks ADD COLUMN worktree_path TEXT"
                )

        project_columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(projects)").fetchall()
        }
        if "task_key_prefix" not in project_columns:
            with self._connection:
                self._connection.execute(
                    "ALTER TABLE projects ADD COLUMN task_key_prefix TEXT NOT NULL DEFAULT ''"
                )
