"""SQLite persistence layer for Foreman."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Sequence

from .models import Event, Project, Run, Sprint, TASK_STATUSES, Task

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    repo_path       TEXT NOT NULL,
    spec_path       TEXT,
    methodology     TEXT NOT NULL DEFAULT 'development',
    workflow_id     TEXT NOT NULL,
    default_branch  TEXT NOT NULL DEFAULT 'main',
    settings_json   TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sprints (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    title           TEXT NOT NULL,
    goal            TEXT,
    status          TEXT NOT NULL DEFAULT 'planned',
    order_index     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sprints_active_project
ON sprints(project_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS tasks (
    id                      TEXT PRIMARY KEY,
    sprint_id               TEXT NOT NULL REFERENCES sprints(id),
    project_id              TEXT NOT NULL REFERENCES projects(id),
    title                   TEXT NOT NULL,
    description             TEXT,
    status                  TEXT NOT NULL DEFAULT 'todo',
    task_type               TEXT NOT NULL DEFAULT 'feature',
    priority                INTEGER NOT NULL DEFAULT 0,
    order_index             INTEGER NOT NULL DEFAULT 0,
    branch_name             TEXT,
    assigned_role           TEXT,
    acceptance_criteria     TEXT,
    blocked_reason          TEXT,
    created_by              TEXT NOT NULL DEFAULT 'human',
    depends_on_task_ids     TEXT NOT NULL DEFAULT '[]',
    workflow_current_step   TEXT,
    workflow_carried_output TEXT,
    step_visit_counts       TEXT NOT NULL DEFAULT '{}',
    created_at              TEXT NOT NULL,
    started_at              TEXT,
    completed_at            TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    project_id      TEXT NOT NULL REFERENCES projects(id),
    role_id         TEXT NOT NULL,
    workflow_step   TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    outcome         TEXT,
    outcome_detail  TEXT,
    agent_backend   TEXT NOT NULL,
    model           TEXT,
    session_id      TEXT,
    branch_name     TEXT,
    prompt_text     TEXT,
    cost_usd        REAL DEFAULT 0.0,
    token_count     INTEGER DEFAULT 0,
    duration_ms     INTEGER,
    retry_count     INTEGER DEFAULT 0,
    started_at      TEXT,
    completed_at    TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES runs(id),
    task_id         TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    role_id         TEXT,
    timestamp       TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_sprint ON tasks(sprint_id);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type, timestamp);
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
        raise ValueError(f"Expected JSON object, received {type(parsed).__name__}.")
    return parsed


def _load_json_list(raw_value: str) -> list[str]:
    parsed = _json_loads(raw_value)
    if parsed in (None, ""):
        return []
    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON array, received {type(parsed).__name__}.")
    return [str(item) for item in parsed]


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        repo_path=row["repo_path"],
        workflow_id=row["workflow_id"],
        spec_path=row["spec_path"],
        methodology=row["methodology"],
        default_branch=row["default_branch"],
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

    def initialize(self) -> None:
        """Create the baseline schema when it does not exist yet."""

        with self._connection:
            self._connection.executescript(SCHEMA_SQL)

    def save_project(self, project: Project) -> Project:
        """Insert or update a project record."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO projects (
                    id, name, repo_path, spec_path, methodology, workflow_id,
                    default_branch, settings_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    repo_path = excluded.repo_path,
                    spec_path = excluded.spec_path,
                    methodology = excluded.methodology,
                    workflow_id = excluded.workflow_id,
                    default_branch = excluded.default_branch,
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
                    workflow_carried_output, step_visit_counts, created_at,
                    started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    def list_events(
        self,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        project_id: str | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """List events filtered by run, task, and or project."""

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
        sql = f"{sql} ORDER BY timestamp ASC, rowid ASC"
        if limit is not None:
            sql = f"{sql} LIMIT ?"
            params.append(limit)

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_event(row) for row in rows]

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
