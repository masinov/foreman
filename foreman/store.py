"""SQLite persistence layer for Foreman."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from .migrations import MIGRATIONS
from .models import CompletionEvidence, DecisionGate, Event, HumanGateDecision, Lease, Project, Run, Sprint, TASK_STATUSES, Task, utc_now_text

_PRUNE_PROTECTED_TASK_STATUSES = ("blocked", "in_progress")

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


class ForemanStore:
    """Persist and query Foreman entities in SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        if str(db_path) == ":memory:":
            self.db_path = ":memory:"
        else:
            path = Path(db_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(path)
        self._connection = sqlite3.connect(self.db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

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
        return applied

    def schema_version(self) -> int:
        """Return the highest migration version applied to this database, or 0."""

        row = self._connection.execute(
            "SELECT MAX(version) AS v FROM schema_migrations"
        ).fetchone()
        if row is None or row["v"] is None:
            return 0
        return int(row["v"])

    def migrate(self) -> list[int]:
        """Apply all unapplied migrations in version order.

        Returns the list of version numbers that were applied in this call.
        Calling migrate() on an up-to-date database is a no-op that returns an
        empty list.
        """

        current = self.schema_version()
        applied: list[int] = []
        now = datetime.now(timezone.utc).isoformat()

        for version, description, sql in sorted(MIGRATIONS, key=lambda m: m[0]):
            if version <= current:
                continue
            with self._connection:
                self._connection.executescript(sql)
                self._connection.execute(
                    "INSERT INTO schema_migrations (version, description, applied_at)"
                    " VALUES (?, ?, ?)",
                    (version, description, now),
                )
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

    def save_project(self, project: Project) -> Project:
        """Insert or update a project record."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO projects (
                    id, name, repo_path, spec_path, methodology, workflow_id,
                    default_branch, autonomy_level, settings_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    repo_path = excluded.repo_path,
                    spec_path = excluded.spec_path,
                    methodology = excluded.methodology,
                    workflow_id = excluded.workflow_id,
                    default_branch = excluded.default_branch,
                    autonomy_level = excluded.autonomy_level,
                    settings_json = excluded.settings_json,
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
        """Insert or update a task record."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO tasks (
                    id, sprint_id, project_id, title, description, status, task_type,
                    priority, order_index, branch_name, assigned_role,
                    acceptance_criteria, blocked_reason, created_by,
                    depends_on_task_ids, workflow_current_step,
                    workflow_carried_output, step_visit_counts, completion_evidence_json,
                    created_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    created_at = excluded.created_at,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at
                """,
                (
                    task.id,
                    task.sprint_id,
                    task.project_id,
                    task.title,
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
                    task.created_at,
                    task.started_at,
                    task.completed_at,
                ),
            )
        return task

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

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO runs (
                    id, task_id, project_id, role_id, workflow_step, status, outcome,
                    outcome_detail, agent_backend, model, session_id, branch_name,
                    prompt_text, cost_usd, token_count, duration_ms, retry_count,
                    started_at, completed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    run.started_at,
                    run.completed_at,
                    run.created_at,
                ),
            )
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

        with self._connection:
            self._connection.execute(
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
        """Delete a task and all its runs and events (cascade)."""

        with self._connection:
            self._connection.execute(
                "DELETE FROM events WHERE run_id IN"
                " (SELECT id FROM runs WHERE task_id = ?)",
                (task_id,),
            )
            self._connection.execute("DELETE FROM runs WHERE task_id = ?", (task_id,))
            self._connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return {"ok": "deleted"}

    def delete_sprint(self, sprint_id: str) -> dict[str, str]:
        """Delete a sprint and all its tasks, runs, and events (cascade)."""

        with self._connection:
            self._connection.execute(
                "DELETE FROM events WHERE run_id IN"
                " (SELECT r.id FROM runs r"
                "  JOIN tasks t ON t.id = r.task_id"
                "  WHERE t.sprint_id = ?)",
                (sprint_id,),
            )
            self._connection.execute(
                "DELETE FROM runs WHERE task_id IN"
                " (SELECT id FROM tasks WHERE sprint_id = ?)",
                (sprint_id,),
            )
            self._connection.execute("DELETE FROM tasks WHERE sprint_id = ?", (sprint_id,))
            self._connection.execute("DELETE FROM sprints WHERE id = ?", (sprint_id,))
        return {"ok": "deleted"}

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

    def acquire_lease(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
        holder_id: str,
        lease_token: str,
        fencing_token: int = 1,
        duration_seconds: float = 300.0,
    ) -> Lease | None:
        """Atomically acquire a lease on a resource.

        Returns the new Lease if acquisition succeeded.
        Returns None if an active lease already exists.
        Expired leases are transitioned to 'expired' before acquisition so they
        never block reacquisition.
        """
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

            # Check whether an active lease already exists for this resource.
            existing = self._connection.execute(
                """
                SELECT id FROM leases
                WHERE project_id = ?
                  AND resource_type = ?
                  AND resource_id = ?
                  AND status = 'active'
                """,
                (project_id, resource_type, resource_id),
            ).fetchone()
            if existing is not None:
                return None

            # Insert the new lease.
            lease_id = f"lease-{uuid4().hex[:12]}"
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
                    holder_id, lease_token, fencing_token,
                    now, now, expires_at,
                ),
            )

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
