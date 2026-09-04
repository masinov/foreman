"""SQLite persistence layer for Foreman."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence, TypeVar
from uuid import uuid4

from .errors import ForemanError
from .migrations import MIGRATIONS
from .models import (
    CompletionEvidence,
    DecisionGate,
    ENGINE_COMMAND_STATUSES,
    ENGINE_COMMANDS,
    EngineCommand,
    EngineLockView,
    Event,
    HumanGateDecision,
    Lease,
    MergeWaiver,
    Project,
    Run,
    Sprint,
    TASK_STATUSES,
    Task,
    utc_now_text,
)

#: Lease resource type for the per-project engine lock. Defined here rather
#: than imported from ``foreman.engine_lock`` because that module imports the
#: store; the string is the schema-level contract both sides agree on.
ENGINE_RESOURCE_TYPE = "engine"

_PRUNE_PROTECTED_TASK_STATUSES = ("blocked", "in_progress")

_T = TypeVar("_T")


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


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _json_loads(raw_value: str) -> Any:
    return json.loads(raw_value) if raw_value else None


def _load_json_dict(raw_value: str) -> dict[str, Any]:
    parsed = _json_loads(raw_value)
    if parsed in (None, ""):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _load_json_list(raw_value: str) -> list[str]:
    parsed = _json_loads(raw_value)
    if parsed in (None, ""):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _serialize_evidence(evidence: Any) -> str:
    """Serialize completion evidence (dataclass or dict) to JSON."""
    if evidence is None:
        return ""
    if isinstance(evidence, dict):
        return _json_dumps(evidence)
    try:
        from dataclasses import asdict
        if isinstance(evidence, CompletionEvidence):
            return _json_dumps(asdict(evidence))
        return _json_dumps(asdict(evidence))
    except Exception:
        return _json_dumps({"error": str(evidence)})


def derive_task_key_prefix(name: str) -> str:
    """Derive a short uppercase project key prefix from a project name.

    Multi-word names use the initials of the first words (e.g. "My Project" ->
    "MP"); single words use their first three letters ("Foreman" -> "FOR").
    Falls back to "TASK" when no alphanumerics are present.
    """

    words = re.findall(r"[A-Za-z0-9]+", name or "")
    if not words:
        return "TASK"
    if len(words) >= 2:
        initials = "".join(word[0] for word in words[:4]).upper()
        if len(initials) >= 2:
            return initials
    return words[0][:3].upper()


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        repo_path=row["repo_path"],
        workflow_id=row["workflow_id"],
        spec_path=row["spec_path"],
        methodology=row["methodology"],
        default_branch=row["default_branch"],
        autonomy_level=row["autonomy_level"] if "autonomy_level" in row.keys() else "supervised",  # type: ignore[assignment]
        settings=_load_json_dict(row["settings_json"]),
        task_key_prefix=row["task_key_prefix"] if "task_key_prefix" in row.keys() else "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_sprint(row: sqlite3.Row) -> Sprint:
    return Sprint(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        goal=row["goal"],
        status=row["status"],
        order_index=row["order_index"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def _row_to_task(row: sqlite3.Row) -> Task:
    raw_evidence = (
        row["completion_evidence_json"]
        if "completion_evidence_json" in row.keys()
        else ""
    )
    evidence_dict = _load_json_dict(raw_evidence) if raw_evidence else None
    completion_evidence: CompletionEvidence | None = (
        CompletionEvidence(**evidence_dict) if isinstance(evidence_dict, dict) else None
    )
    return Task(
        id=row["id"],
        sprint_id=row["sprint_id"],
        project_id=row["project_id"],
        title=row["title"],
        task_key=row["task_key"] if "task_key" in row.keys() else "",
        description=row["description"],
        status=row["status"],
        task_type=row["task_type"],
        priority=row["priority"],
        order_index=row["order_index"],
        branch_name=row["branch_name"],
        assigned_role=row["assigned_role"],
        acceptance_criteria=row["acceptance_criteria"],
        blocked_reason=row["blocked_reason"],
        created_by=row["created_by"],
        depends_on_task_ids=_load_json_list(row["depends_on_task_ids"]),
        workflow_current_step=row["workflow_current_step"],
        workflow_carried_output=row["workflow_carried_output"],
        step_visit_counts=_load_json_dict(row["step_visit_counts"]),
        executor_overrides=(
            _load_json_dict(row["executor_overrides_json"])
            if "executor_overrides_json" in row.keys()
            else {}
        ),
        complexity=row["complexity"] if "complexity" in row.keys() else None,
        completion_evidence=completion_evidence,
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"],
        task_id=row["task_id"],
        project_id=row["project_id"],
        role_id=row["role_id"],
        workflow_step=row["workflow_step"],
        agent_backend=row["agent_backend"],
        status=row["status"],
        outcome=row["outcome"],
        outcome_detail=row["outcome_detail"],
        model=row["model"],
        session_id=row["session_id"],
        branch_name=row["branch_name"],
        prompt_text=row["prompt_text"],
        cost_usd=row["cost_usd"],
        token_count=row["token_count"],
        duration_ms=row["duration_ms"],
        retry_count=row["retry_count"],
        failure_type=row["failure_type"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
    )


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        run_id=row["run_id"],
        task_id=row["task_id"],
        project_id=row["project_id"],
        event_type=row["event_type"],
        timestamp=row["timestamp"],
        role_id=row["role_id"],
        payload=_load_json_dict(row["payload_json"]),
    )


def _row_to_gate(row: sqlite3.Row) -> DecisionGate:
    import json as _json

    raw = row["suggested_order"]
    try:
        suggested_order = _json.loads(raw) if raw else []
    except (ValueError, TypeError):
        suggested_order = []
    return DecisionGate(
        id=row["id"],
        project_id=row["project_id"],
        sprint_id=row["sprint_id"],
        raised_at=row["raised_at"],
        conflict_description=row["conflict_description"],
        suggested_order=suggested_order,
        suggested_reason=row["suggested_reason"] or "",
        status=row["status"],  # type: ignore[assignment]
        resolved_at=row["resolved_at"],
        resolved_by=row["resolved_by"],
    )


def _row_to_lease(row: sqlite3.Row) -> Lease:
    return Lease(
        id=row["id"],
        project_id=row["project_id"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        holder_id=row["holder_id"],
        lease_token=row["lease_token"],
        fencing_token=row["fencing_token"],
        status=row["status"],  # type: ignore[assignment]
        acquired_at=row["acquired_at"],
        heartbeat_at=row["heartbeat_at"],
        expires_at=row["expires_at"],
        released_at=row["released_at"],
    )


def _row_to_engine_command(row: sqlite3.Row) -> EngineCommand:
    return EngineCommand(
        id=row["id"],
        project_id=row["project_id"],
        command=row["command"],  # type: ignore[arg-type]
        requested_by=row["requested_by"],
        task_id=row["task_id"],
        status=row["status"],  # type: ignore[arg-type]
        requested_at=row["requested_at"],
        acknowledged_at=row["acknowledged_at"],
        completed_at=row["completed_at"],
        result_detail=row["result_detail"],
    )


def _row_to_human_gate_decision(row: sqlite3.Row) -> HumanGateDecision:
    return HumanGateDecision(
        id=row["id"],
        task_id=row["task_id"],
        project_id=row["project_id"],
        workflow_step=row["workflow_step"],
        decision=row["decision"],
        note=row["note"],
        decided_by=row["decided_by"] or "human",
        decided_at=row["decided_at"],
        run_id=row["run_id"],
    )


def _row_to_merge_waiver(row: sqlite3.Row) -> MergeWaiver:
    return MergeWaiver(
        id=row["id"],
        task_id=row["task_id"],
        project_id=row["project_id"],
        waiver_type=row["waiver_type"],
        reason=row["reason"],
        approved_by=row["approved_by"],
        approved_at=row["approved_at"],
        branch_name=row["branch_name"],
        head_sha=row["head_sha"],
        base_sha=row["base_sha"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
    )


class ForemanStore:
    """Persist and query Foreman entities in SQLite."""

    #: Default wait for a busy database before a write attempt fails.
    DEFAULT_BUSY_TIMEOUT_SECONDS = 30.0
    #: Retries for hot writes after the busy timeout expires.
    DEFAULT_WRITE_RETRIES = 5

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
        self._connection = sqlite3.connect(self.db_path, timeout=self._busy_timeout_seconds)
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

        attempt = 0
        while True:
            try:
                with self._connection:
                    return operation(self._connection)
            except sqlite3.OperationalError as exc:
                if not _is_locked_error(exc) or attempt >= self._write_retries:
                    raise
                attempt += 1
                time.sleep(min(0.05 * (2 ** attempt), 1.0))

    def __enter__(self) -> ForemanStore:
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

        project_columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(projects)").fetchall()
        }
        if "task_key_prefix" not in project_columns:
            with self._connection:
                self._connection.execute(
                    "ALTER TABLE projects ADD COLUMN task_key_prefix TEXT NOT NULL DEFAULT ''"
                )

    def save_project(self, project: Project) -> Project:
        """Insert or update a project record."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO projects (
                    id, name, repo_path, spec_path, methodology, workflow_id,
                    default_branch, autonomy_level, settings_json, task_key_prefix,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    repo_path = excluded.repo_path,
                    spec_path = excluded.spec_path,
                    methodology = excluded.methodology,
                    workflow_id = excluded.workflow_id,
                    default_branch = excluded.default_branch,
                    autonomy_level = excluded.autonomy_level,
                    settings_json = excluded.settings_json,
                    task_key_prefix = excluded.task_key_prefix,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    project.id,
                    project.name,
                    project.repo_path,
                    project.spec_path,
                    project.methodology,
                    project.workflow_id,
                    project.default_branch,
                    project.autonomy_level,
                    _json_dumps(project.settings),
                    project.task_key_prefix,
                    project.created_at,
                    project.updated_at,
                ),
            )
        return project

    def get_project(self, project_id: str) -> Project | None:
        """Return one project by identifier."""

        row = self._connection.execute(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        return _row_to_project(row) if row else None

    def find_project_by_repo_path(self, repo_path: str) -> Project | None:
        """Return one project by repository path, if it exists."""

        row = self._connection.execute(
            "SELECT * FROM projects WHERE repo_path = ? ORDER BY created_at ASC, id ASC LIMIT 1",
            (repo_path,),
        ).fetchone()
        return _row_to_project(row) if row else None

    def list_projects(self) -> list[Project]:
        """List persisted projects in stable order."""

        rows = self._connection.execute(
            "SELECT * FROM projects ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return [_row_to_project(row) for row in rows]

    def save_sprint(self, sprint: Sprint) -> Sprint:
        """Insert or update a sprint record."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO sprints (
                    id, project_id, title, goal, status, order_index, created_at,
                    started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id = excluded.project_id,
                    title = excluded.title,
                    goal = excluded.goal,
                    status = excluded.status,
                    order_index = excluded.order_index,
                    created_at = excluded.created_at,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at
                """,
                (
                    sprint.id,
                    sprint.project_id,
                    sprint.title,
                    sprint.goal,
                    sprint.status,
                    sprint.order_index,
                    sprint.created_at,
                    sprint.started_at,
                    sprint.completed_at,
                ),
            )
        return sprint

    def get_sprint(self, sprint_id: str) -> Sprint | None:
        """Return one sprint by identifier."""

        row = self._connection.execute(
            "SELECT * FROM sprints WHERE id = ?",
            (sprint_id,),
        ).fetchone()
        return _row_to_sprint(row) if row else None

    def list_sprints(self, project_id: str) -> list[Sprint]:
        """List all sprints for one project."""

        rows = self._connection.execute(
            """
            SELECT * FROM sprints
            WHERE project_id = ?
            ORDER BY order_index ASC, created_at ASC, id ASC
            """,
            (project_id,),
        ).fetchall()
        return [_row_to_sprint(row) for row in rows]

    def get_active_sprint(self, project_id: str) -> Sprint | None:
        """Return the active sprint for one project, if it exists."""

        row = self._connection.execute(
            """
            SELECT * FROM sprints
            WHERE project_id = ? AND status = 'active'
            ORDER BY started_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return _row_to_sprint(row) if row else None

    def get_next_planned_sprint(self, project_id: str) -> Sprint | None:
        """Return the first planned sprint by queue order, or None."""

        row = self._connection.execute(
            """
            SELECT * FROM sprints
            WHERE project_id = ? AND status = 'planned'
            ORDER BY order_index ASC, created_at ASC, id ASC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return _row_to_sprint(row) if row else None

    def save_task(self, task: Task) -> Task:
        """Insert or update a task record.

        Assigns a Jira-style ``task_key`` (e.g. ``FOR-102``) to brand-new tasks.
        The key is write-once: it is set on INSERT and never changed by updates.
        """

        is_new = not task.task_key and self.get_task(task.id) is None

        def _write_task(connection: sqlite3.Connection) -> str:
            # Allocate inside the transaction so the sequence bump and the
            # INSERT commit together; a rolled-back attempt leaves no gap.
            task_key = task.task_key or (self._next_task_key(task.project_id) if is_new else "")
            connection.execute(
                """
                INSERT INTO tasks (
                    id, sprint_id, project_id, title, task_key, description, status, task_type,
                    priority, order_index, branch_name, assigned_role,
                    acceptance_criteria, blocked_reason, created_by,
                    depends_on_task_ids, workflow_current_step,
                    workflow_carried_output, step_visit_counts, completion_evidence_json,
                    executor_overrides_json, complexity,
                    created_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    sprint_id = excluded.sprint_id,
                    project_id = excluded.project_id,
                    title = excluded.title,
                    description = excluded.description,
                    status = excluded.status,
                    task_type = excluded.task_type,
                    priority = excluded.priority,
                    order_index = excluded.order_index,
                    branch_name = excluded.branch_name,
                    assigned_role = excluded.assigned_role,
                    acceptance_criteria = excluded.acceptance_criteria,
                    blocked_reason = excluded.blocked_reason,
                    created_by = excluded.created_by,
                    depends_on_task_ids = excluded.depends_on_task_ids,
                    workflow_current_step = excluded.workflow_current_step,
                    workflow_carried_output = excluded.workflow_carried_output,
                    step_visit_counts = excluded.step_visit_counts,
                    completion_evidence_json = excluded.completion_evidence_json,
                    executor_overrides_json = excluded.executor_overrides_json,
                    complexity = excluded.complexity,
                    created_at = excluded.created_at,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at
                """,
                (
                    task.id,
                    task.sprint_id,
                    task.project_id,
                    task.title,
                    task_key,
                    task.description,
                    task.status,
                    task.task_type,
                    task.priority,
                    task.order_index,
                    task.branch_name,
                    task.assigned_role,
                    task.acceptance_criteria,
                    task.blocked_reason,
                    task.created_by,
                    _json_dumps(task.depends_on_task_ids),
                    task.workflow_current_step,
                    task.workflow_carried_output,
                    _json_dumps(task.step_visit_counts),
                    _serialize_evidence(getattr(task, "completion_evidence", None)),
                    _json_dumps(getattr(task, "executor_overrides", {}) or {}),
                    getattr(task, "complexity", None),
                    task.created_at,
                    task.started_at,
                    task.completed_at,
                ),
            )
            return task_key

        task.task_key = self._write(_write_task)
        return task

    def _ensure_project_key_prefix(self, project_id: str) -> str:
        """Return the project's task-key prefix, deriving and persisting one if unset."""

        row = self._connection.execute(
            "SELECT name, task_key_prefix FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return "TASK"
        prefix = (row["task_key_prefix"] or "").strip()
        if prefix:
            return prefix
        prefix = derive_task_key_prefix(row["name"])
        self._connection.execute(
            "UPDATE projects SET task_key_prefix = ? WHERE id = ?",
            (prefix, project_id),
        )
        return prefix

    def _next_task_key(self, project_id: str) -> str:
        """Allocate the next ``PREFIX-N`` key from the project's sequence.

        Must be called inside the caller's write transaction. The ``UPDATE``
        takes the database write lock, so concurrent writers serialize on the
        sequence and can never mint the same key. Keys that already exist
        (explicitly assigned rows) are skipped.
        """

        prefix = self._ensure_project_key_prefix(project_id)
        while True:
            self._connection.execute(
                "UPDATE projects SET task_key_seq = task_key_seq + 1 WHERE id = ?",
                (project_id,),
            )
            row = self._connection.execute(
                "SELECT task_key_seq FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if row is None:
                return f"{prefix}-1"
            candidate = f"{prefix}-{int(row['task_key_seq'])}"
            taken = self._connection.execute(
                "SELECT 1 FROM tasks WHERE project_id = ? AND task_key = ? LIMIT 1",
                (project_id, candidate),
            ).fetchone()
            if taken is None:
                return candidate

    def _backfill_task_keys(self) -> None:
        """Assign keys to any pre-existing keyless tasks (one-time, idempotent)."""

        missing = self._connection.execute(
            "SELECT 1 FROM tasks WHERE task_key = '' LIMIT 1"
        ).fetchone()
        if missing is None:
            return
        with self._connection:
            project_ids = [
                row["id"] for row in self._connection.execute("SELECT id FROM projects")
            ]
            for project_id in project_ids:
                keyless = self._connection.execute(
                    "SELECT id FROM tasks WHERE project_id = ? AND task_key = '' "
                    "ORDER BY created_at, id",
                    (project_id,),
                ).fetchall()
                for row in keyless:
                    self._connection.execute(
                        "UPDATE tasks SET task_key = ? WHERE id = ?",
                        (self._next_task_key(project_id), row["id"]),
                    )

    def get_task(self, task_id: str) -> Task | None:
        """Return one task by identifier."""

        row = self._connection.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return _row_to_task(row) if row else None

    def list_tasks(
        self,
        *,
        project_id: str | None = None,
        sprint_id: str | None = None,
        status: str | None = None,
        statuses: Sequence[str] | None = None,
    ) -> list[Task]:
        """List tasks filtered by project and or sprint."""

        filters: list[str] = []
        params: list[Any] = []
        if status is not None and statuses is not None:
            raise ValueError("Provide either status or statuses, not both.")
        if project_id is not None:
            filters.append("project_id = ?")
            params.append(project_id)
        if sprint_id is not None:
            filters.append("sprint_id = ?")
            params.append(sprint_id)
        if status is not None:
            statuses = (status,)
        if statuses is not None:
            placeholders = ", ".join("?" for _ in statuses)
            filters.append(f"status IN ({placeholders})")
            params.extend(statuses)

        sql = "SELECT * FROM tasks"
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"{sql} ORDER BY priority ASC, order_index ASC, created_at ASC, id ASC"

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_task(row) for row in rows]

    def next_task_order_index(self, sprint_id: str) -> int:
        """Return the next order_index for a task in a sprint (max + 1)."""
        row = self._connection.execute(
            """
            SELECT MAX(order_index) AS max_idx FROM tasks WHERE sprint_id = ?
            """,
            (sprint_id,),
        ).fetchone()
        max_idx = row["max_idx"] if row and row["max_idx"] is not None else -1
        return max_idx + 1

    def find_task_by_branch(
        self,
        *,
        project_id: str,
        branch_name: str,
    ) -> Task | None:
        """Return the best task match for one persisted branch name."""

        row = self._connection.execute(
            """
            SELECT * FROM tasks
            WHERE project_id = ? AND branch_name = ?
            ORDER BY
                CASE status
                    WHEN 'in_progress' THEN 0
                    WHEN 'blocked' THEN 1
                    WHEN 'todo' THEN 2
                    WHEN 'done' THEN 3
                    WHEN 'cancelled' THEN 4
                    ELSE 5
                END,
                created_at DESC,
                id DESC
            LIMIT 1
            """,
            (project_id, branch_name),
        ).fetchone()
        return _row_to_task(row) if row else None

    def save_run(self, run: Run) -> Run:
        """Insert or update a run record."""

        def _write_run(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO runs (
                    id, task_id, project_id, role_id, workflow_step, status, outcome,
                    outcome_detail, agent_backend, model, session_id, branch_name,
                    prompt_text, cost_usd, token_count, duration_ms, retry_count,
                    failure_type, started_at, completed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    task_id = excluded.task_id,
                    project_id = excluded.project_id,
                    role_id = excluded.role_id,
                    workflow_step = excluded.workflow_step,
                    status = excluded.status,
                    outcome = excluded.outcome,
                    outcome_detail = excluded.outcome_detail,
                    agent_backend = excluded.agent_backend,
                    model = excluded.model,
                    session_id = excluded.session_id,
                    branch_name = excluded.branch_name,
                    prompt_text = excluded.prompt_text,
                    cost_usd = excluded.cost_usd,
                    token_count = excluded.token_count,
                    duration_ms = excluded.duration_ms,
                    retry_count = excluded.retry_count,
                    failure_type = excluded.failure_type,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    created_at = excluded.created_at
                """,
                (
                    run.id,
                    run.task_id,
                    run.project_id,
                    run.role_id,
                    run.workflow_step,
                    run.status,
                    run.outcome,
                    run.outcome_detail,
                    run.agent_backend,
                    run.model,
                    run.session_id,
                    run.branch_name,
                    run.prompt_text,
                    run.cost_usd,
                    run.token_count,
                    run.duration_ms,
                    run.retry_count,
                    run.failure_type,
                    run.started_at,
                    run.completed_at,
                    run.created_at,
                ),
            )

        self._write(_write_run)
        return run

    def get_run(self, run_id: str) -> Run | None:
        """Return one run by identifier."""

        row = self._connection.execute(
            "SELECT * FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        return _row_to_run(row) if row else None

    def list_runs(
        self,
        *,
        task_id: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        statuses: Sequence[str] | None = None,
    ) -> list[Run]:
        """List runs filtered by task and or project."""

        filters: list[str] = []
        params: list[Any] = []
        if status is not None and statuses is not None:
            raise ValueError("Provide either status or statuses, not both.")
        if task_id is not None:
            filters.append("task_id = ?")
            params.append(task_id)
        if project_id is not None:
            filters.append("project_id = ?")
            params.append(project_id)
        if status is not None:
            statuses = (status,)
        if statuses is not None:
            placeholders = ", ".join("?" for _ in statuses)
            filters.append(f"status IN ({placeholders})")
            params.extend(statuses)

        sql = "SELECT * FROM runs"
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"{sql} ORDER BY created_at ASC, rowid ASC"

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_run(row) for row in rows]

    def get_latest_run(self, task_id: str) -> Run | None:
        """Return the most recent run for one task, if it exists."""

        row = self._connection.execute(
            """
            SELECT * FROM runs
            WHERE task_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        return _row_to_run(row) if row else None

    def get_latest_session_id(
        self,
        *,
        task_id: str,
        role_id: str,
        agent_backend: str,
    ) -> str | None:
        """Return the latest persisted non-empty session id for one task role backend scope."""

        row = self._connection.execute(
            """
            SELECT session_id FROM runs
            WHERE task_id = ?
              AND role_id = ?
              AND agent_backend = ?
              AND session_id IS NOT NULL
              AND session_id != ''
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (task_id, role_id, agent_backend),
        ).fetchone()
        if row is None:
            return None
        session_id = row["session_id"]
        return str(session_id) if session_id else None

    def get_latest_event_timestamp(self, run_id: str) -> str | None:
        """Return the latest persisted event timestamp for one run, if any."""

        row = self._connection.execute(
            """
            SELECT timestamp FROM events
            WHERE run_id = ?
            ORDER BY timestamp DESC, rowid DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        timestamp = row["timestamp"]
        return str(timestamp) if timestamp else None

    def save_event(self, event: Event) -> Event:
        """Insert or update an event record."""

        def _write_event(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO events (
                    id, run_id, task_id, project_id, event_type, role_id, timestamp,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    run_id = excluded.run_id,
                    task_id = excluded.task_id,
                    project_id = excluded.project_id,
                    event_type = excluded.event_type,
                    role_id = excluded.role_id,
                    timestamp = excluded.timestamp,
                    payload_json = excluded.payload_json
                """,
                (
                    event.id,
                    event.run_id,
                    event.task_id,
                    event.project_id,
                    event.event_type,
                    event.role_id,
                    event.timestamp,
                    _json_dumps(event.payload),
                ),
            )

        self._write(_write_event)
        return event

    def get_event(self, event_id: str) -> Event | None:
        """Return one event by identifier."""

        row = self._connection.execute(
            "SELECT * FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        return _row_to_event(row) if row else None

    def _get_event_cursor_marker(self, event_id: str) -> sqlite3.Row | None:
        """Return the timestamp and rowid used for incremental event queries."""

        return self._connection.execute(
            "SELECT timestamp, rowid FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()

    def list_events(
        self,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        project_id: str | None = None,
        after_event_id: str | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """List events filtered by run, task, and or project."""

        filters: list[str] = []
        params: list[Any] = []
        if run_id is not None:
            filters.append("e.run_id = ?")
            params.append(run_id)
        if task_id is not None:
            filters.append("e.task_id = ?")
            params.append(task_id)
        if project_id is not None:
            filters.append("e.project_id = ?")
            params.append(project_id)
        if after_event_id is not None:
            marker = self._get_event_cursor_marker(after_event_id)
            if marker is None:
                return []
            filters.append(
                """
                (
                    e.timestamp > ?
                    OR (e.timestamp = ? AND e.rowid > ?)
                )
                """
            )
            params.extend([marker["timestamp"], marker["timestamp"], marker["rowid"]])

        sql = "SELECT e.* FROM events e"
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"{sql} ORDER BY e.timestamp ASC, e.rowid ASC"
        if limit is not None:
            sql = f"{sql} LIMIT ?"
            params.append(limit)

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_sprint_events(
        self,
        sprint_id: str,
        *,
        after_event_id: str | None = None,
        before_event_id: str | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """List sprint-scoped events in display order.

        Pass ``after_event_id`` to fetch events newer than a known cursor
        (used by the SSE stream to deliver incremental updates).
        Pass ``before_event_id`` to fetch events older than a known cursor
        (used by the activity panel load-more control).
        """

        params: list[Any] = [sprint_id]

        if after_event_id is not None:
            marker = self._get_event_cursor_marker(after_event_id)
            if marker is None:
                return []
            sql = """
                SELECT e.*
                FROM events e
                INNER JOIN tasks t ON t.id = e.task_id
                WHERE t.sprint_id = ?
                AND (
                    e.timestamp > ?
                    OR (e.timestamp = ? AND e.rowid > ?)
                )
                ORDER BY e.timestamp ASC, e.rowid ASC
            """
            params.extend([marker["timestamp"], marker["timestamp"], marker["rowid"]])
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            rows = self._connection.execute(sql, tuple(params)).fetchall()
            return [_row_to_event(row) for row in rows]

        if before_event_id is not None:
            marker = self._get_event_cursor_marker(before_event_id)
            if marker is None:
                return []
            sql = """
                SELECT e.*
                FROM events e
                INNER JOIN tasks t ON t.id = e.task_id
                WHERE t.sprint_id = ?
                AND (
                    e.timestamp < ?
                    OR (e.timestamp = ? AND e.rowid < ?)
                )
                ORDER BY e.timestamp DESC, e.rowid DESC
            """
            params.extend([marker["timestamp"], marker["timestamp"], marker["rowid"]])
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            rows = self._connection.execute(sql, tuple(params)).fetchall()
            events = [_row_to_event(row) for row in rows]
            events.reverse()
            return events

        # No cursor — return all events in display order, optionally limited.
        sql = """
            SELECT e.*
            FROM events e
            INNER JOIN tasks t ON t.id = e.task_id
            WHERE t.sprint_id = ?
            ORDER BY e.timestamp ASC, e.rowid ASC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_recent_sprint_events(self, sprint_id: str, *, limit: int = 50) -> list[Event]:
        """Return the most recent sprint events while preserving display order."""

        if limit <= 0:
            return []

        rows = self._connection.execute(
            """
            SELECT e.*
            FROM events e
            INNER JOIN tasks t ON t.id = e.task_id
            WHERE t.sprint_id = ?
            ORDER BY e.timestamp DESC, e.rowid DESC
            LIMIT ?
            """,
            (sprint_id, limit),
        ).fetchall()
        events = [_row_to_event(row) for row in rows]
        events.reverse()
        return events

    def list_recent_events(
        self,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
    ) -> list[Event]:
        """Return the most recent events while preserving display order."""

        if limit <= 0:
            return []

        filters: list[str] = []
        params: list[Any] = []
        if run_id is not None:
            filters.append("run_id = ?")
            params.append(run_id)
        if task_id is not None:
            filters.append("task_id = ?")
            params.append(task_id)
        if project_id is not None:
            filters.append("project_id = ?")
            params.append(project_id)

        sql = "SELECT * FROM events"
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"{sql} ORDER BY timestamp DESC, rowid DESC LIMIT ?"
        params.append(limit)

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        events = [_row_to_event(row) for row in rows]
        events.reverse()
        return events

    def prune_old_events(
        self,
        *,
        project_id: str,
        older_than: str,
    ) -> int:
        """Delete project events older than one cutoff while preserving active-work history."""

        with self._connection:
            cursor = self._connection.execute(
                f"""
                DELETE FROM events
                WHERE project_id = ?
                  AND timestamp < ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM tasks
                      WHERE tasks.id = events.task_id
                        AND tasks.status IN ({", ".join("?" for _ in _PRUNE_PROTECTED_TASK_STATUSES)})
                  )
                """,
                (
                    project_id,
                    older_than,
                    *_PRUNE_PROTECTED_TASK_STATUSES,
                ),
            )
        return int(cursor.rowcount)

    _PRUNE_TERMINAL_RUN_STATUSES: tuple[str, ...] = (
        "completed",
        "failed",
        "killed",
        "timeout",
    )

    def prune_old_runs(
        self,
        *,
        project_id: str,
        older_than: str,
    ) -> int:
        """Delete terminal runs older than one cutoff and their dependent events.

        Runs whose task is still blocked or in_progress are preserved regardless
        of age.  Events attached to the deleted runs are removed first to satisfy
        the foreign-key constraint on events.run_id.  Both deletes execute inside
        a single transaction.

        Returns the number of run rows deleted.
        """

        qualifying_sql = """
            SELECT id FROM runs
            WHERE project_id = ?
              AND completed_at < ?
              AND status IN ({statuses})
              AND NOT EXISTS (
                  SELECT 1 FROM tasks
                  WHERE tasks.id = runs.task_id
                    AND tasks.status IN ({protected})
              )
        """.format(
            statuses=", ".join("?" for _ in self._PRUNE_TERMINAL_RUN_STATUSES),
            protected=", ".join("?" for _ in _PRUNE_PROTECTED_TASK_STATUSES),
        )
        qualifying_params = (
            project_id,
            older_than,
            *self._PRUNE_TERMINAL_RUN_STATUSES,
            *_PRUNE_PROTECTED_TASK_STATUSES,
        )

        with self._connection:
            self._connection.execute(
                f"DELETE FROM events WHERE run_id IN ({qualifying_sql})",
                qualifying_params,
            )
            # Gate decisions are audit records: keep them, drop the run link.
            self._connection.execute(
                f"UPDATE human_gate_decisions SET run_id = NULL"
                f" WHERE run_id IN ({qualifying_sql})",
                qualifying_params,
            )
            cursor = self._connection.execute(
                f"DELETE FROM runs WHERE id IN ({qualifying_sql})",
                qualifying_params,
            )
        return int(cursor.rowcount)

    def strip_old_run_prompts(
        self,
        *,
        project_id: str,
        older_than: str,
    ) -> int:
        """Null out prompt_text on terminal runs older than one cutoff.

        The run record, telemetry, and status are preserved; only the stored
        prompt text is removed to reduce storage.  Active-work protection is not
        applied here because stripping text from a run record is non-destructive.

        Returns the number of run rows updated.
        """

        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE runs
                SET prompt_text = NULL
                WHERE project_id = ?
                  AND completed_at < ?
                  AND prompt_text IS NOT NULL
                  AND status IN ({statuses})
                """.format(
                    statuses=", ".join("?" for _ in self._PRUNE_TERMINAL_RUN_STATUSES)
                ),
                (
                    project_id,
                    older_than,
                    *self._PRUNE_TERMINAL_RUN_STATUSES,
                ),
            )
        return int(cursor.rowcount)

    def run_totals(
        self,
        *,
        project_id: str | None = None,
        sprint_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, int | float]:
        """Return aggregate run metrics for a project, sprint, or task scope."""

        filters: list[str] = []
        params: list[Any] = []
        join_clause = ""

        if sprint_id is not None:
            join_clause = " JOIN tasks ON tasks.id = runs.task_id"
            filters.append("tasks.sprint_id = ?")
            params.append(sprint_id)
        if project_id is not None:
            filters.append("runs.project_id = ?")
            params.append(project_id)
        if task_id is not None:
            filters.append("runs.task_id = ?")
            params.append(task_id)

        sql = """
            SELECT
                COUNT(runs.id) AS run_count,
                COALESCE(SUM(runs.cost_usd), 0.0) AS total_cost_usd,
                COALESCE(SUM(runs.token_count), 0) AS total_token_count,
                COALESCE(SUM(runs.duration_ms), 0) AS total_duration_ms,
                COALESCE(
                    SUM(
                        CASE
                            WHEN runs.token_count > 0 AND runs.cost_usd = 0 THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS zero_cost_token_runs
            FROM runs
        """
        sql = f"{sql}{join_clause}"
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"

        row = self._connection.execute(sql, tuple(params)).fetchone()
        assert row is not None
        return {
            "run_count": int(row["run_count"]),
            "total_cost_usd": float(row["total_cost_usd"]),
            "total_token_count": int(row["total_token_count"]),
            "total_duration_ms": int(row["total_duration_ms"]),
            "zero_cost_token_runs": int(row["zero_cost_token_runs"]),
        }

    def task_run_totals(
        self,
        *,
        project_id: str | None = None,
        sprint_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return per-task aggregate run metrics for one project or sprint."""

        filters: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            filters.append("tasks.project_id = ?")
            params.append(project_id)
        if sprint_id is not None:
            filters.append("tasks.sprint_id = ?")
            params.append(sprint_id)

        sql = """
            SELECT
                tasks.id AS task_id,
                tasks.title AS task_title,
                tasks.status AS task_status,
                tasks.task_type AS task_type,
                tasks.branch_name AS branch_name,
                tasks.assigned_role AS assigned_role,
                COUNT(runs.id) AS run_count,
                COALESCE(SUM(runs.cost_usd), 0.0) AS total_cost_usd,
                COALESCE(SUM(runs.token_count), 0) AS total_token_count,
                COALESCE(SUM(runs.duration_ms), 0) AS total_duration_ms
            FROM tasks
            LEFT JOIN runs ON runs.task_id = tasks.id
        """
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"""
            {sql}
            GROUP BY
                tasks.id,
                tasks.title,
                tasks.status,
                tasks.task_type,
                tasks.branch_name,
                tasks.assigned_role
            ORDER BY tasks.priority ASC, tasks.order_index ASC, tasks.created_at ASC, tasks.id ASC
        """

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [
            {
                "task_id": str(row["task_id"]),
                "task_title": str(row["task_title"]),
                "task_status": str(row["task_status"]),
                "task_type": str(row["task_type"]),
                "branch_name": row["branch_name"],
                "assigned_role": row["assigned_role"],
                "run_count": int(row["run_count"]),
                "total_cost_usd": float(row["total_cost_usd"]),
                "total_token_count": int(row["total_token_count"]),
                "total_duration_ms": int(row["total_duration_ms"]),
            }
            for row in rows
        ]

    def delete_task(self, task_id: str) -> dict[str, str]:
        """Delete a task and everything that hangs off it, in one transaction."""

        with self._connection:
            self._delete_task_dependents(self._connection, "SELECT ? AS id", (task_id,))
            self._connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return {"ok": "deleted"}

    def delete_sprint(self, sprint_id: str) -> dict[str, str]:
        """Delete a sprint and everything that hangs off it, in one transaction."""

        with self._connection:
            self._delete_task_dependents(
                self._connection,
                "SELECT id FROM tasks WHERE sprint_id = ?",
                (sprint_id,),
            )
            self._connection.execute("DELETE FROM tasks WHERE sprint_id = ?", (sprint_id,))
            self._connection.execute(
                "DELETE FROM decision_gates WHERE sprint_id = ?", (sprint_id,)
            )
            self._connection.execute("DELETE FROM sprints WHERE id = ?", (sprint_id,))
        return {"ok": "deleted"}

    @staticmethod
    def _delete_task_dependents(
        connection: sqlite3.Connection,
        task_ids_sql: str,
        params: tuple[Any, ...],
    ) -> None:
        """Delete rows that reference the tasks selected by ``task_ids_sql``.

        Covers events, runs, human gate decisions, merge waivers, and task
        leases. Ordered so every foreign key is satisfied even on databases
        whose gate tables predate the ON DELETE rules from migration 14.
        """

        connection.execute(
            f"DELETE FROM events WHERE task_id IN ({task_ids_sql})"
            f" OR run_id IN (SELECT id FROM runs WHERE task_id IN ({task_ids_sql}))",
            (*params, *params),
        )
        connection.execute(
            f"DELETE FROM human_gate_decisions WHERE task_id IN ({task_ids_sql})",
            params,
        )
        connection.execute(
            f"DELETE FROM merge_waivers WHERE task_id IN ({task_ids_sql})",
            params,
        )
        connection.execute(
            f"DELETE FROM leases WHERE resource_type = 'task'"
            f" AND resource_id IN ({task_ids_sql})",
            params,
        )
        connection.execute(
            f"DELETE FROM runs WHERE task_id IN ({task_ids_sql})",
            params,
        )

    def count_projects(self) -> int:
        """Return the number of tracked projects."""

        row = self._connection.execute(
            "SELECT COUNT(*) AS value FROM projects"
        ).fetchone()
        return int(row["value"])

    def count_active_sprints(self) -> int:
        """Return the number of active sprints across all projects."""

        row = self._connection.execute(
            "SELECT COUNT(*) AS value FROM sprints WHERE status = 'active'"
        ).fetchone()
        return int(row["value"])

    def task_counts(
        self,
        project_id: str | None = None,
        sprint_id: str | None = None,
    ) -> dict[str, int]:
        """Return task counts keyed by task status."""

        sql = "SELECT status, COUNT(*) AS value FROM tasks"
        filters: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            filters.append("project_id = ?")
            params.append(project_id)
        if sprint_id is not None:
            filters.append("sprint_id = ?")
            params.append(sprint_id)
        if filters:
            sql = f"{sql} WHERE {' AND '.join(filters)}"
        sql = f"{sql} GROUP BY status"

        counts = {status: 0 for status in TASK_STATUSES}
        for row in self._connection.execute(sql, tuple(params)).fetchall():
            counts[str(row["status"])] = int(row["value"])
        return counts

    # ── Decision gates ────────────────────────────────────────────────────────

    def save_decision_gate(self, gate: DecisionGate) -> DecisionGate:
        """Insert or update a decision gate record."""
        import json as _json

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO decision_gates (
                    id, project_id, sprint_id, raised_at,
                    conflict_description, suggested_order, suggested_reason,
                    status, resolved_at, resolved_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    resolved_at = excluded.resolved_at,
                    resolved_by = excluded.resolved_by
                """,
                (
                    gate.id,
                    gate.project_id,
                    gate.sprint_id,
                    gate.raised_at,
                    gate.conflict_description,
                    _json.dumps(gate.suggested_order),
                    gate.suggested_reason,
                    gate.status,
                    gate.resolved_at,
                    gate.resolved_by,
                ),
            )
        return gate

    def get_decision_gate(self, gate_id: str) -> DecisionGate | None:
        """Return one decision gate by id."""
        row = self._connection.execute(
            "SELECT * FROM decision_gates WHERE id = ?", (gate_id,)
        ).fetchone()
        return _row_to_gate(row) if row else None

    def list_decision_gates(
        self,
        project_id: str,
        *,
        status: str | None = None,
    ) -> list[DecisionGate]:
        """List decision gates for a project, optionally filtered by status."""
        if status is not None:
            rows = self._connection.execute(
                "SELECT * FROM decision_gates WHERE project_id = ? AND status = ? ORDER BY raised_at DESC",
                (project_id, status),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM decision_gates WHERE project_id = ? ORDER BY raised_at DESC",
                (project_id,),
            ).fetchall()
        return [_row_to_gate(row) for row in rows]

    # ── Human gate decisions ──────────────────────────────────────────────────

    def save_human_gate_decision(self, decision: HumanGateDecision) -> HumanGateDecision:
        """Insert a human gate decision record."""
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO human_gate_decisions (
                    id, task_id, project_id, workflow_step,
                    decision, note, decided_by, decided_at, run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.id,
                    decision.task_id,
                    decision.project_id,
                    decision.workflow_step,
                    decision.decision,
                    decision.note,
                    decision.decided_by,
                    decision.decided_at,
                    decision.run_id,
                ),
            )
        return decision

    def get_human_gate_decision(
        self,
        task_id: str,
        workflow_step: str,
    ) -> HumanGateDecision | None:
        """Return the most recent human gate decision for a task/step."""
        row = self._connection.execute(
            """
            SELECT * FROM human_gate_decisions
            WHERE task_id = ? AND workflow_step = ?
            ORDER BY decided_at DESC
            LIMIT 1
            """,
            (task_id, workflow_step),
        ).fetchone()
        return _row_to_human_gate_decision(row) if row else None

    # ── Merge Waivers ─────────────────────────────────────────────────────────────

    def save_merge_waiver(self, waiver: MergeWaiver) -> MergeWaiver:
        """Insert a merge waiver record."""
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO merge_waivers (
                    id, task_id, project_id, waiver_type, reason,
                    approved_by, approved_at, branch_name, head_sha, base_sha,
                    expires_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    waiver.id,
                    waiver.task_id,
                    waiver.project_id,
                    waiver.waiver_type,
                    waiver.reason,
                    waiver.approved_by,
                    waiver.approved_at,
                    waiver.branch_name,
                    waiver.head_sha,
                    waiver.base_sha,
                    waiver.expires_at,
                    waiver.revoked_at,
                ),
            )
        return waiver

    def get_merge_waiver(self, waiver_id: str) -> MergeWaiver | None:
        """Return a merge waiver by ID."""
        row = self._connection.execute(
            "SELECT * FROM merge_waivers WHERE id = ?",
            (waiver_id,),
        ).fetchone()
        return _row_to_merge_waiver(row) if row else None

    def get_active_merge_waiver(
        self,
        task_id: str,
        branch_name: str,
        head_sha: str,
        waiver_type: str | None = None,
    ) -> MergeWaiver | None:
        """Return an active (non-revoked, non-expired) waiver for a task and branch head.

        A waiver is active if:
        - revoked_at is NULL
        - expires_at is NULL or in the future
        - branch_name matches
        - head_sha matches (waiver is tied to specific branch state)
        - waiver_type matches if specified
        """
        now = utc_now_text()
        row = self._connection.execute(
            """
            SELECT * FROM merge_waivers
            WHERE task_id = ?
              AND branch_name = ?
              AND head_sha = ?
              AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > ?)
              AND (? IS NULL OR waiver_type = ?)
            ORDER BY approved_at DESC
            LIMIT 1
            """,
            (task_id, branch_name, head_sha, now, waiver_type, waiver_type),
        ).fetchone()
        return _row_to_merge_waiver(row) if row else None

    def revoke_merge_waiver(self, waiver_id: str) -> bool:
        """Revoke a merge waiver by setting revoked_at. Returns True if found and revoked."""
        now = utc_now_text()
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE merge_waivers SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (now, waiver_id),
            )
            return cursor.rowcount > 0

    # ── Meta-agent sessions and turns ───────────────────────────────────────────

    def get_meta_session(self, project_id: str) -> str | None:
        """Return the stored Claude Code resume session id for a project, if any."""
        row = self._connection.execute(
            "SELECT session_id FROM meta_sessions WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return row["session_id"] if row else None

    def save_meta_session(self, project_id: str, session_id: str | None) -> None:
        """Upsert the meta-agent resume session id for a project."""
        now = utc_now_text()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO meta_sessions (project_id, session_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    updated_at = excluded.updated_at
                """,
                (project_id, session_id, now),
            )

    def append_meta_turn(
        self,
        project_id: str,
        *,
        role: str,
        text: str,
        tool_uses: list[dict[str, Any]] | None = None,
        origin: str = "chat",
    ) -> str:
        """Append one conversation turn and return its generated id."""
        import json as _json
        from uuid import uuid4

        turn_id = uuid4().hex
        now = utc_now_text()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO meta_turns (
                    id, project_id, role, text, tool_uses_json, origin, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    project_id,
                    role,
                    text,
                    _json.dumps(tool_uses or []),
                    origin,
                    now,
                ),
            )
        return turn_id

    def list_meta_turns(
        self,
        project_id: str,
        *,
        limit: int = 50,
        before_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Return up to ``limit`` turns oldest-first plus a ``has_more`` flag.

        When ``before_id`` is given, returns turns created strictly before that
        turn (older history), supporting cursor-based "load older" paging that
        mirrors the sprint-event endpoint.
        """
        import json as _json

        params: list[Any] = [project_id]
        cursor_clause = ""
        if before_id is not None:
            anchor = self._connection.execute(
                "SELECT created_at FROM meta_turns WHERE id = ?",
                (before_id,),
            ).fetchone()
            if anchor is not None:
                cursor_clause = " AND (created_at < ? OR (created_at = ? AND id < ?))"
                params.extend([anchor["created_at"], anchor["created_at"], before_id])

        # Fetch newest-first with one extra row to detect more history, then
        # reverse so callers receive turns in chronological order.
        params.append(limit + 1)
        rows = self._connection.execute(
            f"""
            SELECT id, role, text, tool_uses_json, origin, created_at
            FROM meta_turns
            WHERE project_id = ?{cursor_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

        has_more = len(rows) > limit
        rows = rows[:limit]
        turns = [
            {
                "id": row["id"],
                "role": row["role"],
                "text": row["text"],
                "tool_uses": _json.loads(row["tool_uses_json"] or "[]"),
                "origin": row["origin"],
                "created_at": row["created_at"],
            }
            for row in reversed(rows)
        ]
        return turns, has_more

    def has_consumed_supervision_event(self, project_id: str, event_id: str) -> bool:
        """Return True if a supervision turn already consumed ``event_id``.

        Idempotency guard for the supervise endpoint: the consumed
        ``engine.attention_needed`` event id is stored in the user turn's
        ``tool_uses_json`` metadata.
        """
        like = f'%"consumed_event_id": "{event_id}"%'
        row = self._connection.execute(
            """
            SELECT 1 FROM meta_turns
            WHERE project_id = ? AND origin = 'supervision'
              AND tool_uses_json LIKE ?
            LIMIT 1
            """,
            (project_id, like),
        ).fetchone()
        return row is not None

    def clear_meta_session(self, project_id: str) -> None:
        """Delete the stored session row and all turns for a project."""
        with self._connection:
            self._connection.execute(
                "DELETE FROM meta_turns WHERE project_id = ?", (project_id,)
            )
            self._connection.execute(
                "DELETE FROM meta_sessions WHERE project_id = ?", (project_id,)
            )

    # ── Leases ────────────────────────────────────────────────────────────────────

    def get_lease(self, lease_id: str) -> Lease | None:
        """Return one lease by identifier."""
        row = self._connection.execute(
            "SELECT * FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        return _row_to_lease(row) if row else None

    def get_active_lease(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
    ) -> Lease | None:
        """Return the active lease for one resource, or None."""
        row = self._connection.execute(
            """
            SELECT * FROM leases
            WHERE project_id = ?
              AND resource_type = ?
              AND resource_id = ?
              AND status = 'active'
            LIMIT 1
            """,
            (project_id, resource_type, resource_id),
        ).fetchone()
        return _row_to_lease(row) if row else None

    def expire_resource_leases(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
        force: bool = False,
    ) -> int:
        """Mark all active leases for one resource as expired. Returns count of expired leases.

        By default, only leases whose ``expires_at`` is already in the past are
        transitioned. Pass ``force=True`` to expire every active lease for the
        resource regardless of ``expires_at``; used by recovery when the
        original holder is known to be gone and a future lease expiry cannot be
        waited for.
        """
        now = utc_now_text()
        with self._connection:
            if force:
                cursor = self._connection.execute(
                    """
                    UPDATE leases
                    SET status = 'expired'
                    WHERE project_id = ?
                      AND resource_type = ?
                      AND resource_id = ?
                      AND status = 'active'
                    """,
                    (project_id, resource_type, resource_id),
                )
            else:
                cursor = self._connection.execute(
                    """
                    UPDATE leases
                    SET status = 'expired'
                    WHERE project_id = ?
                      AND resource_type = ?
                      AND resource_id = ?
                      AND status = 'active'
                      AND expires_at < ?
                    """,
                    (project_id, resource_type, resource_id, now),
                )
            return cursor.rowcount

    def acquire_lease(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
        holder_id: str,
        lease_token: str,
        duration_seconds: float = 300.0,
    ) -> Lease | None:
        """Atomically acquire a lease on a resource.

        Returns the new Lease if acquisition succeeded.
        Returns None if an active lease already exists (enforced by the DB's
        unique partial index on active leases).
        Expired leases are transitioned to 'expired' before insertion so they
        do not block reacquisition.

        The fencing_token is auto-incremented: new leases get MAX(existing) + 1.
        """
        import sqlite3
        from .leases import compute_lease_expiry

        now = utc_now_text()
        expires_at = compute_lease_expiry(duration_seconds)

        with self._connection:
            # Transition any expired leases for this resource to 'expired'.
            self._connection.execute(
                """
                UPDATE leases
                SET status = 'expired'
                WHERE project_id = ?
                  AND resource_type = ?
                  AND resource_id = ?
                  AND status = 'active'
                  AND expires_at < ?
                """,
                (project_id, resource_type, resource_id, now),
            )

            # Compute next fencing token: MAX(existing) + 1 for this resource
            max_token_row = self._connection.execute(
                """
                SELECT COALESCE(MAX(fencing_token), 0) + 1 AS next_token
                FROM leases
                WHERE project_id = ?
                  AND resource_type = ?
                  AND resource_id = ?
                """,
                (project_id, resource_type, resource_id),
            ).fetchone()
            next_fencing_token: int = max_token_row["next_token"] if max_token_row else 1

            # Insert the new lease. The unique partial index enforces that only
            # one active lease per resource exists at a time.
            lease_id = f"lease-{uuid4().hex[:12]}"
            try:
                self._connection.execute(
                    """
                    INSERT INTO leases (
                        id, project_id, resource_type, resource_id, holder_id,
                        lease_token, fencing_token, status,
                        acquired_at, heartbeat_at, expires_at, released_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, NULL)
                    """,
                    (
                        lease_id, project_id, resource_type, resource_id,
                        holder_id, lease_token, next_fencing_token,
                        now, now, expires_at,
                    ),
                )
            except sqlite3.IntegrityError:
                # Another connection inserted an active lease between our expiry
                # update and insert; this is the expected race result.
                return None

        return self.get_lease(lease_id)

    def renew_lease(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
        holder_id: str,
        lease_token: str,
        duration_seconds: float = 300.0,
    ) -> Lease | None:
        """Renew an active lease if the caller holds it with the correct token.

        Returns the renewed Lease on success.
        Returns None if: no active lease, holder_id mismatch, or token mismatch.
        """
        from .leases import compute_lease_expiry, is_lease_expired

        now = utc_now_text()
        expires_at = compute_lease_expiry(duration_seconds)

        with self._connection:
            row = self._connection.execute(
                """
                SELECT * FROM leases
                WHERE project_id = ?
                  AND resource_type = ?
                  AND resource_id = ?
                  AND status = 'active'
                """,
                (project_id, resource_type, resource_id),
            ).fetchone()
            if row is None:
                return None

            lease = _row_to_lease(row)

            # Validate holder and token.
            if lease.holder_id != holder_id or lease.lease_token != lease_token:
                return None

            # Check expiry (edge case: clock skew or concurrent expiry).
            if is_lease_expired(lease):
                self._connection.execute(
                    "UPDATE leases SET status = 'expired' WHERE id = ?",
                    (lease.id,),
                )
                return None

            # Renew: update heartbeat and expiry.
            self._connection.execute(
                """
                UPDATE leases
                SET heartbeat_at = ?, expires_at = ?
                WHERE id = ?
                """,
                (now, expires_at, lease.id),
            )

        return self.get_lease(lease.id)

    def release_lease(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
        holder_id: str,
        lease_token: str,
    ) -> bool:
        """Release an active lease if the caller holds it with the correct token.

        Returns True on successful release.
        Returns False if: no active lease, holder_id mismatch, or token mismatch.
        """
        now = utc_now_text()

        with self._connection:
            row = self._connection.execute(
                """
                SELECT * FROM leases
                WHERE project_id = ?
                  AND resource_type = ?
                  AND resource_id = ?
                  AND status = 'active'
                """,
                (project_id, resource_type, resource_id),
            ).fetchone()
            if row is None:
                return False

            lease = _row_to_lease(row)

            if lease.holder_id != holder_id or lease.lease_token != lease_token:
                return False

            self._connection.execute(
                """
                UPDATE leases
                SET status = 'released', released_at = ?
                WHERE id = ?
                """,
                (now, lease.id),
            )

        return True

    def expire_leases(
        self,
        *,
        project_id: str | None = None,
        holder_id: str | None = None,
        older_than_seconds: float | None = None,
    ) -> int:
        """Mark active leases as expired based on heartbeat age or holder.

        If older_than_seconds is provided, expires leases whose heartbeat is
        older than that threshold. If holder_id is provided, only expires
        leases for that holder. If both provided, both conditions must match.

        Returns the number of leases expired.
        """
        from datetime import timedelta

        conditions = ["status = 'active'"]
        params: list[Any] = []

        if older_than_seconds is not None:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z")
            conditions.append("heartbeat_at < ?")
            params.append(cutoff)

        if holder_id is not None:
            conditions.append("holder_id = ?")
            params.append(holder_id)

        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)

        where_clause = " AND ".join(conditions)

        with self._connection:
            cursor = self._connection.execute(
                f"""
                UPDATE leases
                SET status = 'expired'
                WHERE {where_clause}
                """,
                tuple(params),
            )
        return int(cursor.rowcount)

    def list_leases(
        self,
        *,
        project_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        holder_id: str | None = None,
        status: str | None = None,
    ) -> list[Lease]:
        """List leases with optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)
        if resource_type is not None:
            conditions.append("resource_type = ?")
            params.append(resource_type)
        if resource_id is not None:
            conditions.append("resource_id = ?")
            params.append(resource_id)
        if holder_id is not None:
            conditions.append("holder_id = ?")
            params.append(holder_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)

        sql = "SELECT * FROM leases"
        if conditions:
            sql = f"{sql} WHERE {' AND '.join(conditions)}"
        sql = f"{sql} ORDER BY acquired_at ASC"

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_lease(row) for row in rows]

    # ── Engine commands ───────────────────────────────────────────────────────────

    def enqueue_engine_command(
        self,
        *,
        project_id: str,
        command: str,
        requested_by: str,
        task_id: str | None = None,
        command_id: str | None = None,
    ) -> EngineCommand:
        """Queue one control instruction for the project's resident engine.

        The insert commits on this connection, which bumps ``PRAGMA
        data_version`` for every *other* connection — so a resident engine
        sitting in its idle wait notices the command without polling any table.
        """

        if command not in ENGINE_COMMANDS:
            raise ValueError(
                f"Unknown engine command {command!r}. "
                f"Expected one of: {', '.join(ENGINE_COMMANDS)}."
            )
        record = EngineCommand(
            id=command_id or f"cmd-{uuid4().hex[:12]}",
            project_id=project_id,
            command=command,  # type: ignore[arg-type]
            requested_by=requested_by,
            task_id=task_id,
        )

        def _write(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO engine_commands (
                    id, project_id, command, task_id, requested_by, requested_at,
                    status, acknowledged_at, completed_at, result_detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.project_id,
                    record.command,
                    record.task_id,
                    record.requested_by,
                    record.requested_at,
                    record.status,
                    record.acknowledged_at,
                    record.completed_at,
                    record.result_detail,
                ),
            )

        self._write(_write)
        return record

    def get_engine_command(self, command_id: str) -> EngineCommand | None:
        """Return one engine command by identifier."""

        row = self._connection.execute(
            "SELECT * FROM engine_commands WHERE id = ?",
            (command_id,),
        ).fetchone()
        return _row_to_engine_command(row) if row else None

    def list_engine_commands(
        self,
        project_id: str,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[EngineCommand]:
        """List a project's engine commands, most recently requested first."""

        conditions = ["project_id = ?"]
        params: list[Any] = [project_id]
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        params.append(max(0, int(limit)))
        rows = self._connection.execute(
            f"""
            SELECT * FROM engine_commands
            WHERE {' AND '.join(conditions)}
            ORDER BY requested_at DESC, rowid DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_row_to_engine_command(row) for row in rows]

    def next_pending_engine_command(self, project_id: str) -> EngineCommand | None:
        """Return the oldest pending command for a project, or None.

        Ordering is by request time so commands are applied in the order they
        were asked for; ``rowid`` breaks ties between two commands queued
        inside the same timestamp tick.
        """

        row = self._connection.execute(
            """
            SELECT * FROM engine_commands
            WHERE project_id = ? AND status = 'pending'
            ORDER BY requested_at ASC, rowid ASC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return _row_to_engine_command(row) if row else None

    def mark_engine_command(
        self,
        command_id: str,
        status: str,
        *,
        detail: str | None = None,
    ) -> EngineCommand | None:
        """Advance one command's lifecycle and record why.

        ``acknowledged`` stamps ``acknowledged_at``; ``completed`` and
        ``rejected`` stamp ``completed_at``. Returns the updated row, or None
        when the command no longer exists.
        """

        if status not in ENGINE_COMMAND_STATUSES:
            raise ValueError(
                f"Unknown engine command status {status!r}. "
                f"Expected one of: {', '.join(ENGINE_COMMAND_STATUSES)}."
            )
        now = utc_now_text()

        def _write(connection: sqlite3.Connection) -> None:
            assignments = ["status = ?"]
            params: list[Any] = [status]
            if status == "acknowledged":
                assignments.append("acknowledged_at = ?")
                params.append(now)
            elif status in {"completed", "rejected"}:
                assignments.append("completed_at = ?")
                params.append(now)
            if detail is not None:
                assignments.append("result_detail = ?")
                params.append(detail)
            params.append(command_id)
            connection.execute(
                f"UPDATE engine_commands SET {', '.join(assignments)} WHERE id = ?",
                tuple(params),
            )

        self._write(_write)
        return self.get_engine_command(command_id)

    def get_engine_lock(self, project_id: str) -> EngineLockView | None:
        """Return a token-free view of the project's engine lease, or None.

        This is the read side of :class:`~foreman.engine_lock.EngineLock`: it
        answers "is an engine resident on this project, whose is it, and how
        fresh is its heartbeat" without handing out the token that would let
        the reader release someone else's lock.
        """

        lease = self.get_active_lease(
            project_id=project_id,
            resource_type=ENGINE_RESOURCE_TYPE,
            resource_id=project_id,
        )
        if lease is None:
            return None
        return EngineLockView(
            project_id=lease.project_id,
            holder_id=lease.holder_id,
            acquired_at=lease.acquired_at,
            heartbeat_at=lease.heartbeat_at,
            expires_at=lease.expires_at,
        )
