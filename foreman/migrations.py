"""Ordered schema migrations for the Foreman SQLite store.

Each entry is a tuple of (version, description, sql).  Versions must be
consecutive integers starting at 1.  The migration runner in
``ForemanStore.migrate()`` applies any version whose id is not yet recorded in
the ``schema_migrations`` table.

Rules for adding a migration:
- Append to the end of MIGRATIONS.  Never reorder or remove existing entries.
- Separate statements with semicolons.  The runner splits the script into
  statements and applies every statement of one migration plus its ledger row
  inside a single ``BEGIN IMMEDIATE`` transaction, so a failing migration
  leaves the database exactly as it was.
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
    (
        4,
        "add decision_gates table for supervised-mode conflict notifications",
        """
        CREATE TABLE IF NOT EXISTS decision_gates (
            id                   TEXT PRIMARY KEY,
            project_id           TEXT NOT NULL REFERENCES projects(id),
            sprint_id            TEXT NOT NULL REFERENCES sprints(id),
            raised_at            TEXT NOT NULL,
            conflict_description TEXT NOT NULL,
            suggested_order      TEXT NOT NULL DEFAULT '[]',
            suggested_reason     TEXT NOT NULL DEFAULT '',
            status               TEXT NOT NULL DEFAULT 'pending',
            resolved_at          TEXT,
            resolved_by          TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_decision_gates_project
        ON decision_gates(project_id, status);
        """,
    ),
    (
        5,
        "add completion_evidence_json to tasks for structured completion verdicts",
        """
        ALTER TABLE tasks ADD COLUMN completion_evidence_json TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        6,
        "add leases table for first-class resource locking",
        """
        CREATE TABLE IF NOT EXISTS leases (
            id              TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL,
            resource_type   TEXT NOT NULL,
            resource_id     TEXT NOT NULL,
            holder_id       TEXT NOT NULL,
            lease_token     TEXT NOT NULL,
            fencing_token   INTEGER NOT NULL DEFAULT 1,
            status          TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'released', 'expired')),
            acquired_at     TEXT NOT NULL,
            heartbeat_at    TEXT NOT NULL,
            expires_at      TEXT NOT NULL,
            released_at     TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_leases_project_resource
        ON leases(project_id, resource_type, resource_id)
        WHERE status = 'active';

        CREATE INDEX IF NOT EXISTS idx_leases_holder
        ON leases(holder_id)
        WHERE status = 'active';

        CREATE INDEX IF NOT EXISTS idx_leases_expires
        ON leases(expires_at)
        WHERE status = 'active';
        """,
    ),
    (
        7,
        "add human_gate_decisions table for durable human approval records",
        """
        CREATE TABLE IF NOT EXISTS human_gate_decisions (
            id              TEXT PRIMARY KEY,
            task_id         TEXT NOT NULL REFERENCES tasks(id),
            project_id      TEXT NOT NULL REFERENCES projects(id),
            workflow_step   TEXT NOT NULL,
            decision        TEXT NOT NULL CHECK (decision IN ('approve', 'deny', 'steer')),
            note            TEXT,
            decided_by      TEXT NOT NULL DEFAULT 'human',
            decided_at      TEXT NOT NULL,
            run_id          TEXT REFERENCES runs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_human_gate_decisions_task
        ON human_gate_decisions(task_id, workflow_step);
        """,
    ),
    (
        8,
        "add failure_type to runs for classified failure diagnosis",
        """
        ALTER TABLE runs ADD COLUMN failure_type TEXT;
        """,
    ),
    (
        9,
        "add unique partial index enforcing one active lease per resource",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_leases_active_resource_unique
        ON leases(project_id, resource_type, resource_id)
        WHERE status = 'active';
        """,
    ),
    (
        10,
        "add merge_waivers table for human override of proof gate",
        """
        CREATE TABLE IF NOT EXISTS merge_waivers (
            id              TEXT PRIMARY KEY,
            task_id         TEXT NOT NULL,
            project_id      TEXT NOT NULL,
            waiver_type     TEXT NOT NULL,
            reason          TEXT NOT NULL,
            approved_by     TEXT NOT NULL,
            approved_at     TEXT NOT NULL,
            branch_name     TEXT NOT NULL,
            head_sha        TEXT NOT NULL,
            base_sha        TEXT NOT NULL,
            expires_at      TEXT,
            revoked_at      TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_merge_waivers_task
        ON merge_waivers(task_id);
        """,
    ),
    (
        11,
        "add meta_sessions and meta_turns for durable meta-agent chat",
        """
        CREATE TABLE IF NOT EXISTS meta_sessions (
            project_id   TEXT PRIMARY KEY REFERENCES projects(id),
            session_id   TEXT,
            updated_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meta_turns (
            id             TEXT PRIMARY KEY,
            project_id     TEXT NOT NULL REFERENCES projects(id),
            role           TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            text           TEXT NOT NULL,
            tool_uses_json TEXT NOT NULL DEFAULT '[]',
            origin         TEXT NOT NULL DEFAULT 'chat',
            created_at     TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_meta_turns_project
        ON meta_turns(project_id, created_at);
        """,
    ),
    (
        12,
        "add per-task executor overrides and architect complexity",
        """
        ALTER TABLE tasks ADD COLUMN executor_overrides_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE tasks ADD COLUMN complexity TEXT;
        """,
    ),
    (
        13,
        "add Jira-style task keys (per-project prefix + task key)",
        """
        ALTER TABLE projects ADD COLUMN task_key_prefix TEXT NOT NULL DEFAULT '';
        ALTER TABLE tasks ADD COLUMN task_key TEXT NOT NULL DEFAULT '';

        CREATE INDEX IF NOT EXISTS idx_tasks_task_key
        ON tasks(project_id, task_key);
        """,
    ),
    (
        14,
        "store safety: cascading gate tables, events(task_id) index, task-key sequence",
        """
        -- human_gate_decisions: rebuild with ON DELETE rules so pruning runs
        -- keeps the decision (run_id -> NULL) and deleting a task or project
        -- removes its decisions instead of failing the foreign-key check.
        CREATE TABLE human_gate_decisions_v14 (
            id              TEXT PRIMARY KEY,
            task_id         TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            workflow_step   TEXT NOT NULL,
            decision        TEXT NOT NULL CHECK (decision IN ('approve', 'deny', 'steer')),
            note            TEXT,
            decided_by      TEXT NOT NULL DEFAULT 'human',
            decided_at      TEXT NOT NULL,
            run_id          TEXT REFERENCES runs(id) ON DELETE SET NULL
        );
        INSERT INTO human_gate_decisions_v14 (
            id, task_id, project_id, workflow_step, decision, note, decided_by,
            decided_at, run_id
        )
        SELECT id, task_id, project_id, workflow_step, decision, note, decided_by,
               decided_at, run_id
        FROM human_gate_decisions;
        DROP TABLE human_gate_decisions;
        ALTER TABLE human_gate_decisions_v14 RENAME TO human_gate_decisions;
        CREATE INDEX IF NOT EXISTS idx_human_gate_decisions_task
        ON human_gate_decisions(task_id, workflow_step);

        -- decision_gates: rebuild so deleting a sprint or project cascades.
        CREATE TABLE decision_gates_v14 (
            id                   TEXT PRIMARY KEY,
            project_id           TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            sprint_id            TEXT NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
            raised_at            TEXT NOT NULL,
            conflict_description TEXT NOT NULL,
            suggested_order      TEXT NOT NULL DEFAULT '[]',
            suggested_reason     TEXT NOT NULL DEFAULT '',
            status               TEXT NOT NULL DEFAULT 'pending',
            resolved_at          TEXT,
            resolved_by          TEXT
        );
        INSERT INTO decision_gates_v14 (
            id, project_id, sprint_id, raised_at, conflict_description,
            suggested_order, suggested_reason, status, resolved_at, resolved_by
        )
        SELECT id, project_id, sprint_id, raised_at, conflict_description,
               suggested_order, suggested_reason, status, resolved_at, resolved_by
        FROM decision_gates;
        DROP TABLE decision_gates;
        ALTER TABLE decision_gates_v14 RENAME TO decision_gates;
        CREATE INDEX IF NOT EXISTS idx_decision_gates_project
        ON decision_gates(project_id, status);

        -- The sprint activity query joins events to tasks by task_id.
        CREATE INDEX IF NOT EXISTS idx_events_task
        ON events(task_id, timestamp);

        -- Per-project task-key sequence, bumped inside the task INSERT
        -- transaction so concurrent writers can never mint the same key.
        ALTER TABLE projects ADD COLUMN task_key_seq INTEGER NOT NULL DEFAULT 0;

        -- Blank out duplicate keys minted by the old scan-based allocator
        -- (keep the earliest row); the store backfills blanks from the sequence.
        UPDATE tasks SET task_key = ''
        WHERE task_key <> ''
          AND rowid NOT IN (
              SELECT MIN(rowid) FROM tasks GROUP BY project_id, task_key
          );

        UPDATE projects SET task_key_seq = COALESCE((
            SELECT MAX(CAST(substr(t.task_key, instr(t.task_key, '-') + 1) AS INTEGER))
            FROM tasks t
            WHERE t.project_id = projects.id
              AND t.task_key <> ''
              AND instr(t.task_key, '-') > 0
        ), 0);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_task_key_unique
        ON tasks(project_id, task_key) WHERE task_key <> '';
        """,
    ),
    (
        15,
        "add engine_commands: the durable control channel to a resident engine",
        """
        -- Signals are the only way to talk to a `foreman serve` process, and a
        -- signal cannot say "run this task" or survive the engine being down.
        -- This table is that channel: a caller inserts a row, the resident
        -- engine picks it up on its next poll, and the row records what the
        -- engine did with it.
        CREATE TABLE IF NOT EXISTS engine_commands (
            id              TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            command         TEXT NOT NULL
                            CHECK (command IN ('pause', 'resume', 'run_task',
                                               'stop_task', 'shutdown')),
            task_id         TEXT REFERENCES tasks(id) ON DELETE CASCADE,
            requested_by    TEXT NOT NULL,
            requested_at    TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'acknowledged',
                                              'completed', 'rejected')),
            acknowledged_at TEXT,
            completed_at    TEXT,
            result_detail   TEXT
        );

        -- The engine's hot query is "oldest pending command for this project";
        -- the CLI and dashboard read the same three columns to show history.
        CREATE INDEX IF NOT EXISTS idx_engine_commands_project_status
        ON engine_commands(project_id, status, requested_at);
        """,
    ),
    (
        16,
        "add tasks.worktree_path: the Foreman-owned checkout a task runs in",
        """
        -- Every task now runs in its own git worktree instead of the
        -- operator's checkout. The path is persisted so the CLI, the
        -- dashboard, and a restarted engine can find the tree a paused task
        -- was working in without recomputing the layout. Nullable: tasks that
        -- never reached a develop step have no worktree, and a project whose
        -- worktree root moves gets a new path on the next visit.
        ALTER TABLE tasks ADD COLUMN worktree_path TEXT;
        """,
    ),
    (
        17,
        "add api_tokens and task source columns: work arriving from other systems",
        """
        -- Intake tokens are the credential another system presents to hand
        -- Foreman work (MANUAL Intake API). Only the SHA-256 of the secret is
        -- stored: the secret itself is shown once at creation and is not
        -- recoverable from this table, so a stolen database yields no usable
        -- credential. `scopes_json` is a JSON array; `intake` is the only
        -- scope today, and the column exists so later scopes do not need a
        -- table rebuild.
        CREATE TABLE IF NOT EXISTS api_tokens (
            id           TEXT PRIMARY KEY,
            project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            token_hash   TEXT NOT NULL,
            scopes_json  TEXT NOT NULL DEFAULT '["intake"]',
            created_by   TEXT NOT NULL DEFAULT 'human',
            created_at   TEXT NOT NULL,
            last_used_at TEXT,
            revoked_at   TEXT
        );

        -- Authentication looks a token up by hash on every intake request, and
        -- two tokens must never share one hash.
        CREATE UNIQUE INDEX IF NOT EXISTS idx_api_tokens_hash
        ON api_tokens(token_hash);

        -- `foreman token list` and the project view read a project's tokens
        -- newest first.
        CREATE INDEX IF NOT EXISTS idx_api_tokens_project
        ON api_tokens(project_id, created_at);

        -- Where a task came from, when it did not come from a person: the
        -- calling system, its own identifier for the work, a link back to it,
        -- and who reported it there. All nullable -- tasks created through the
        -- CLI or the dashboard have no external source.
        ALTER TABLE tasks ADD COLUMN source_system TEXT;
        ALTER TABLE tasks ADD COLUMN source_ref TEXT;
        ALTER TABLE tasks ADD COLUMN source_url TEXT;
        ALTER TABLE tasks ADD COLUMN reporter TEXT;

        -- Intake is idempotent on (project, system, external ref); this index
        -- is the lookup that decides create-vs-return on every call.
        CREATE INDEX IF NOT EXISTS idx_tasks_source
        ON tasks(project_id, source_system, source_ref);
        """,
    ),
    (
        18,
        "add notification destinations and deliveries: telling people what happened",
        """
        -- Where a project wants to be told. `webhook` is the only kind today
        -- because it is the only one that needs no credential beyond a URL;
        -- `kind` exists so a later transport (chat, email) is a row rather
        -- than a table. `config_json` carries the per-kind detail (extra
        -- headers, the environment variable holding a signing secret) so a
        -- new transport's options do not require a migration.
        CREATE TABLE IF NOT EXISTS notification_destinations (
            id          TEXT PRIMARY KEY,
            project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            kind        TEXT NOT NULL DEFAULT 'webhook',
            target      TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            enabled     INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        -- A destination's name is how a person refers to it on the CLI, so it
        -- has to be unique inside the project.
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_destinations_name
        ON notification_destinations(project_id, name);

        -- One row per (destination, notifiable event). The row is the record:
        -- it survives the process that tried to send it, so a destination that
        -- was down is retried by whoever runs next rather than forgotten, and
        -- a destination that stayed down leaves `failed` behind with the error
        -- instead of silence.
        CREATE TABLE IF NOT EXISTS notification_deliveries (
            id              TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            destination_id  TEXT NOT NULL REFERENCES notification_destinations(id)
                            ON DELETE CASCADE,
            task_id         TEXT,
            event_id        TEXT,
            kind            TEXT NOT NULL,
            payload_json    TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'delivered', 'failed')),
            attempts        INTEGER NOT NULL DEFAULT 0,
            max_attempts    INTEGER NOT NULL DEFAULT 5,
            next_attempt_at TEXT NOT NULL,
            last_error      TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            delivered_at    TEXT
        );

        -- The delivery worker's only hot query: what is due for this project.
        CREATE INDEX IF NOT EXISTS idx_notification_deliveries_due
        ON notification_deliveries(project_id, status, next_attempt_at);

        -- The engine may emit the same attention turn to the same destination
        -- twice (a retried pass, two orchestrators racing); the acceptance
        -- criterion is one delivery per turn, so the database enforces it.
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_deliveries_event
        ON notification_deliveries(destination_id, event_id)
        WHERE event_id IS NOT NULL;
        """,
    ),
    (
        19,
        "add the token split to runs: input, output, cache read, cache creation",
        """
        -- `token_count` stays what it always was (fresh input plus output).
        -- A long agent session mostly re-reads cached context, which the
        -- single number hid entirely; the four parts are stored as reported.
        ALTER TABLE runs ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE runs ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE runs ADD COLUMN cache_read_tokens INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE runs ADD COLUMN cache_creation_tokens INTEGER NOT NULL DEFAULT 0;
        """,
    ),
    (
        20,
        "refuse statuses and types the engine does not know",
        """
        -- The older tables were created without CHECK constraints, and SQLite
        -- cannot add one to an existing table without rebuilding it. Triggers
        -- give the same guarantee without touching the rows: a status, task
        -- type, complexity or autonomy level outside the vocabulary in
        -- foreman/models.py is refused whoever writes it. Rows that already
        -- hold such a value stay readable; they cannot be written back
        -- unchanged in that column.
        CREATE TRIGGER IF NOT EXISTS tasks_status_insert_guard
        BEFORE INSERT ON tasks
        WHEN NEW.status NOT IN ('triage', 'todo', 'in_progress', 'blocked', 'done', 'cancelled')
        BEGIN
            SELECT RAISE(ABORT, 'invalid tasks.status');
        END;

        CREATE TRIGGER IF NOT EXISTS tasks_status_update_guard
        BEFORE UPDATE OF status ON tasks
        WHEN NEW.status NOT IN ('triage', 'todo', 'in_progress', 'blocked', 'done', 'cancelled')
        BEGIN
            SELECT RAISE(ABORT, 'invalid tasks.status');
        END;

        CREATE TRIGGER IF NOT EXISTS tasks_task_type_insert_guard
        BEFORE INSERT ON tasks
        WHEN NEW.task_type NOT IN ('feature', 'fix', 'refactor', 'docs', 'spike', 'chore')
        BEGIN
            SELECT RAISE(ABORT, 'invalid tasks.task_type');
        END;

        CREATE TRIGGER IF NOT EXISTS tasks_task_type_update_guard
        BEFORE UPDATE OF task_type ON tasks
        WHEN NEW.task_type NOT IN ('feature', 'fix', 'refactor', 'docs', 'spike', 'chore')
        BEGIN
            SELECT RAISE(ABORT, 'invalid tasks.task_type');
        END;

        CREATE TRIGGER IF NOT EXISTS tasks_complexity_insert_guard
        BEFORE INSERT ON tasks
        WHEN NEW.complexity IS NOT NULL AND NEW.complexity NOT IN ('small', 'medium', 'large')
        BEGIN
            SELECT RAISE(ABORT, 'invalid tasks.complexity');
        END;

        CREATE TRIGGER IF NOT EXISTS tasks_complexity_update_guard
        BEFORE UPDATE OF complexity ON tasks
        WHEN NEW.complexity IS NOT NULL AND NEW.complexity NOT IN ('small', 'medium', 'large')
        BEGIN
            SELECT RAISE(ABORT, 'invalid tasks.complexity');
        END;

        CREATE TRIGGER IF NOT EXISTS sprints_status_insert_guard
        BEFORE INSERT ON sprints
        WHEN NEW.status NOT IN ('planned', 'active', 'completed', 'cancelled')
        BEGIN
            SELECT RAISE(ABORT, 'invalid sprints.status');
        END;

        CREATE TRIGGER IF NOT EXISTS sprints_status_update_guard
        BEFORE UPDATE OF status ON sprints
        WHEN NEW.status NOT IN ('planned', 'active', 'completed', 'cancelled')
        BEGIN
            SELECT RAISE(ABORT, 'invalid sprints.status');
        END;

        CREATE TRIGGER IF NOT EXISTS runs_status_insert_guard
        BEFORE INSERT ON runs
        WHEN NEW.status NOT IN ('pending', 'running', 'completed', 'failed', 'killed', 'timeout')
        BEGIN
            SELECT RAISE(ABORT, 'invalid runs.status');
        END;

        CREATE TRIGGER IF NOT EXISTS runs_status_update_guard
        BEFORE UPDATE OF status ON runs
        WHEN NEW.status NOT IN ('pending', 'running', 'completed', 'failed', 'killed', 'timeout')
        BEGIN
            SELECT RAISE(ABORT, 'invalid runs.status');
        END;

        CREATE TRIGGER IF NOT EXISTS projects_autonomy_level_insert_guard
        BEFORE INSERT ON projects
        WHEN NEW.autonomy_level NOT IN ('directed', 'supervised', 'autonomous')
        BEGIN
            SELECT RAISE(ABORT, 'invalid projects.autonomy_level');
        END;

        CREATE TRIGGER IF NOT EXISTS projects_autonomy_level_update_guard
        BEFORE UPDATE OF autonomy_level ON projects
        WHEN NEW.autonomy_level NOT IN ('directed', 'supervised', 'autonomous')
        BEGIN
            SELECT RAISE(ABORT, 'invalid projects.autonomy_level');
        END;
        """,
    ),
    (
        21,
        "the backlog: a sprint row of kind 'backlog', the declined status, intake queues become backlogs",
        """
        -- ADR-0021. Every existing row is a sprint. A backlog is one row per
        -- project that is never listed, counted, activated or run as a sprint.
        ALTER TABLE sprints ADD COLUMN kind TEXT NOT NULL DEFAULT 'sprint';

        CREATE TRIGGER IF NOT EXISTS sprints_kind_insert_guard
        BEFORE INSERT ON sprints
        WHEN NEW.kind NOT IN ('sprint', 'backlog')
        BEGIN
            SELECT RAISE(ABORT, 'invalid sprints.kind');
        END;

        CREATE TRIGGER IF NOT EXISTS sprints_kind_update_guard
        BEFORE UPDATE OF kind ON sprints
        WHEN NEW.kind NOT IN ('sprint', 'backlog')
        BEGIN
            SELECT RAISE(ABORT, 'invalid sprints.kind');
        END;

        -- A backlog never becomes active, so the engine can never run it,
        -- whoever writes the row. Its stored status is always 'planned'.
        CREATE TRIGGER IF NOT EXISTS sprints_backlog_status_insert_guard
        BEFORE INSERT ON sprints
        WHEN NEW.kind = 'backlog' AND NEW.status != 'planned'
        BEGIN
            SELECT RAISE(ABORT, 'a backlog cannot be active, completed or cancelled');
        END;

        CREATE TRIGGER IF NOT EXISTS sprints_backlog_status_update_guard
        BEFORE UPDATE OF status, kind ON sprints
        WHEN NEW.kind = 'backlog' AND NEW.status != 'planned'
        BEGIN
            SELECT RAISE(ABORT, 'a backlog cannot be active, completed or cancelled');
        END;

        CREATE UNIQUE INDEX IF NOT EXISTS idx_sprints_backlog_project
        ON sprints(project_id) WHERE kind = 'backlog';

        -- `declined` joins the task status vocabulary (migration 20).
        DROP TRIGGER IF EXISTS tasks_status_insert_guard;
        CREATE TRIGGER tasks_status_insert_guard
        BEFORE INSERT ON tasks
        WHEN NEW.status NOT IN
            ('triage', 'todo', 'in_progress', 'blocked', 'done', 'cancelled', 'declined')
        BEGIN
            SELECT RAISE(ABORT, 'invalid tasks.status');
        END;

        DROP TRIGGER IF EXISTS tasks_status_update_guard;
        CREATE TRIGGER tasks_status_update_guard
        BEFORE UPDATE OF status ON tasks
        WHEN NEW.status NOT IN
            ('triage', 'todo', 'in_progress', 'blocked', 'done', 'cancelled', 'declined')
        BEGIN
            SELECT RAISE(ABORT, 'invalid tasks.status');
        END;

        -- Each intake queue (ADR-0013, `<project>-intake`) becomes the
        -- project's backlog. Its waiting work, filed (`triage`) or accepted
        -- (`todo`), moves to a new `<project>-backlog` row. Work the queue
        -- already started or finished stays where it is, history intact.
        INSERT INTO sprints (id, project_id, title, goal, status, order_index, created_at, kind)
        SELECT p.id || '-backlog', p.id, 'Backlog',
               'Work that is filed or accepted and not yet planned into a sprint. '
               || 'The engine never runs it.',
               'planned', 0, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), 'backlog'
        FROM projects p
        WHERE EXISTS (SELECT 1 FROM sprints q WHERE q.id = p.id || '-intake')
          AND NOT EXISTS (SELECT 1 FROM sprints b WHERE b.project_id = p.id AND b.kind = 'backlog')
          AND NOT EXISTS (SELECT 1 FROM sprints c WHERE c.id = p.id || '-backlog');

        UPDATE tasks
        SET sprint_id = (
            SELECT b.id FROM sprints b
            WHERE b.project_id = tasks.project_id AND b.kind = 'backlog'
        )
        WHERE sprint_id = project_id || '-intake'
          AND status IN ('triage', 'todo')
          AND EXISTS (
            SELECT 1 FROM sprints b
            WHERE b.project_id = tasks.project_id AND b.kind = 'backlog'
          );

        DELETE FROM sprints
        WHERE id = project_id || '-intake'
          AND kind = 'sprint'
          AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.sprint_id = sprints.id)
          AND NOT EXISTS (SELECT 1 FROM decision_gates g WHERE g.sprint_id = sprints.id);

        -- A queue left holding only finished work is finished too; one still
        -- running keeps running until the engine completes it.
        UPDATE sprints
        SET status = 'completed',
            completed_at = COALESCE(completed_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = project_id || '-intake'
          AND kind = 'sprint'
          AND status = 'planned'
          AND NOT EXISTS (
            SELECT 1 FROM tasks t
            WHERE t.sprint_id = sprints.id AND t.status NOT IN ('done', 'cancelled')
          );
        """,
    ),
    (
        22,
        "proposals: changes the manager proposes and a person confirms (ADR-0022)",
        """
        CREATE TABLE IF NOT EXISTS proposals (
            id              TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            proposed_by     TEXT NOT NULL,
            session_id      TEXT,
            turn_id         TEXT,
            reason          TEXT NOT NULL,
            operations_json TEXT NOT NULL,
            leaves_json     TEXT NOT NULL DEFAULT '[]',
            names_json      TEXT NOT NULL DEFAULT '{}',
            state           TEXT NOT NULL DEFAULT 'proposed'
                CHECK (state IN ('proposed', 'confirmed', 'declined', 'failed')),
            created_at      TEXT NOT NULL,
            decided_by      TEXT,
            decided_at      TEXT,
            outcome_json    TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_proposals_project
        ON proposals(project_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_proposals_turn
        ON proposals(turn_id) WHERE turn_id IS NOT NULL;
        """,
    ),
    (
        23,
        "runs: the commit the task branch pointed at when the run finished",
        """
        ALTER TABLE runs ADD COLUMN commit_sha TEXT;
        """,
    ),
]
