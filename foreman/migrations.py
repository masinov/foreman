"""Ordered schema migrations for the Foreman SQLite store.

Each entry is a tuple of (version, description, sql).  Versions must be
consecutive integers starting at 1.  The migration runner in
``ForemanStore.migrate()`` applies any version whose id is not yet recorded in
the ``schema_migrations`` table.

Rules for adding a migration:
- Append to the end of MIGRATIONS.  Never reorder or remove existing entries.
- Use a single SQL statement per migration where possible.  For multi-statement
  migrations, separate statements with semicolons; the runner calls
  ``executescript`` which handles that correctly.
- Prefer ``ALTER TABLE ... ADD COLUMN`` for additive schema changes.
- Never mutate data inside a migration unless the change is idempotent and safe
  to replay on a live database.
"""

from __future__ import annotations

# Each tuple: (version: int, description: str, sql: str)
MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "baseline schema — projects, sprints, tasks, runs, events",
        """
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
        """,
    ),
    (
        2,
        "add idx_runs_project_completed for efficient run retention queries",
        """
        CREATE INDEX IF NOT EXISTS idx_runs_project_completed
        ON runs(project_id, completed_at);
        """,
    ),
    (
        3,
        "add autonomy_level to projects",
        """
        ALTER TABLE projects ADD COLUMN autonomy_level TEXT NOT NULL DEFAULT 'supervised';
        """,
    ),
]
