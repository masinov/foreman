# PR Summary: fix/store-concurrency-safety

## Summary

Sprint 53, slice 1. Closes the persistence defects from the production
readiness review that would stop or corrupt an unattended engine: retention
and deletes that violated foreign keys, a single SQLite file shared by three
processes with no lock strategy, migrations that could half-apply, task keys
that two writers could both mint, and project settings that the engine read
raw so validated defaults never applied.

## Scope

- **Migration 14** (`foreman/migrations.py`): rebuilds `human_gate_decisions`
  with `task_id`/`project_id ON DELETE CASCADE` and `run_id ON DELETE SET
  NULL`, rebuilds `decision_gates` with cascading `project_id`/`sprint_id`,
  adds `idx_events_task ON events(task_id, timestamp)` for the sprint
  activity query, adds `projects.task_key_seq`, blanks duplicate task keys
  minted by the old scan allocator, seeds the sequence from existing keys, and
  adds a unique partial index on `(project_id, task_key)`.
- **Atomic migrations** (`ForemanStore.migrate`): each migration's statements
  and its ledger row run inside one `BEGIN IMMEDIATE` transaction, split with
  `sqlite3.complete_statement` so comments and literals are safe; a failure
  rolls back and raises `MigrationError`; the ledger is re-checked inside the
  transaction so concurrent migrators cannot double-apply.
- **Multi-process sharing**: file-backed stores open with a 30 s busy timeout,
  `journal_mode=WAL`, and `synchronous=NORMAL`; `save_task`, `save_run`, and
  `save_event` go through a `_write` helper that retries lock errors with
  backoff. Scaffolded `.gitignore` files and this repo's ignore the
  `.foreman.db-wal` / `-shm` sidecars.
- **Task keys**: `_next_task_key` bumps the per-project sequence inside the
  insert transaction and skips explicitly assigned keys; the key is committed
  with the row so a rolled-back attempt leaves no gap.
- **Dependent-aware deletes**: `delete_task` and `delete_sprint` remove events,
  runs, gate decisions, merge waivers, task leases, and decision gates in one
  transaction; `prune_old_runs` nulls the run link on gate decisions instead
  of failing.
- **Dashboard**: `create_dashboard_app` initializes the schema once;
  per-request stores only open a connection.
- **Settings**: `ProjectSettings` gains optional `run_retention_days` and
  `prompt_retention_days`, `max_infra_retries`, and
  `active_run_recovery_timeout_minutes`; `event_retention_days` is now
  optional and off by default. `resolve_project_settings` validates at the
  start of `run_project` and in `prune_old_history`; the dashboard settings
  endpoint and `foreman config --set` reject invalid values without saving.

## Files changed

- `foreman/migrations.py`, `foreman/store.py`, `foreman/settings.py`,
  `foreman/orchestrator.py`, `foreman/dashboard_backend.py`,
  `foreman/dashboard_service.py`, `foreman/cli.py`, `foreman/scaffold.py`,
  `.gitignore`
- `tests/test_store_safety.py` (new, 20 tests), `tests/test_scaffold.py`,
  `tests/test_cli.py`
- `docs/sprints/current.md`, `docs/sprints/backlog.md`, `docs/STATUS.md`,
  `docs/reviews/production-readiness-review.md` (new), `docs/MANUAL.md`,
  `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `CHANGELOG.md`

## Migrations

- 14 — store safety. Verified against a copy of this repo's dogfood database:
  applies cleanly, `PRAGMA foreign_key_check` is empty, WAL enabled, sequence
  seeded from the existing key.

## Risks

- **Behavior change:** event retention is now opt-in. Databases that relied on
  the 90-day default in the settings model were never actually pruned (the
  engine read the raw dict), so nothing changes in practice, but the documented
  default moved.
- **Behavior change:** a project with invalid settings now refuses to run
  instead of running on silent defaults. The error names the project and the
  offending value.
- WAL needs a local filesystem; on media where the pragma fails the store
  silently keeps the rollback journal.
- Migration 14 rebuilds two child tables. Because the runner is now atomic, a
  failure leaves the database at version 13 untouched.

## Tests

- `./venv/bin/python -m unittest discover -s tests` — 605 passing (was 585;
  +20 in `tests/test_store_safety.py`).
- `scripts/validate_repo_memory.py` clean; `git diff --check` clean.
- Manual: `foreman db migrate --db <copy of .foreman.db>` applied
  migration 14; `foreman config foreman` validates under the new model.

## Acceptance criteria satisfied

- pruning and deletes no longer raise `IntegrityError` once a gate decision
  or decision gate exists; a gate decision survives run pruning with its run
  link nulled,
- engine, dashboard, and CLI can write to one file with WAL and a real busy
  timeout, and hot writes retry after a foreign lock,
- a failing migration leaves the schema version and tables unchanged,
- eight concurrent writers mint eight distinct task keys,
- invalid settings are rejected at every write boundary and at run start.

## Follow-ups

- Sprint 53 slices 2–6 (see `docs/sprints/current.md`).
- Phase 1: split audit-grade events from telemetry before enabling retention
  by default; move the database out of the repository directory; ledger the
  task-key backfill and retire `_repair_known_schema_drift`.
