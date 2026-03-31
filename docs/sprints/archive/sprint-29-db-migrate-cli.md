# Sprint 29: `foreman db` CLI surface

- Sprint: `sprint-29-db-migrate-cli`
- Status: done
- Branch: `feat/db-migrate-cli`
- Goal: add `foreman db migrate` and `foreman db version` CLI surfaces for
  operators to inspect schema version and apply pending migrations explicitly

## Summary

Added a `db` subcommand group to the Foreman CLI with two sub-commands:

- `foreman db version` — queries `ForemanStore.schema_version()` and reports
  the current migration level; handles the pre-migration-framework case where
  `schema_migrations` doesn't exist by catching `sqlite3.OperationalError` and
  printing an informative message rather than crashing.
- `foreman db migrate` — calls `store.initialize()` (idempotent: creates the
  `schema_migrations` table if absent, then applies unapplied migrations in
  version order) and reports each applied migration with its version number and
  description; confirms when the schema is already up to date.

Changed `ForemanStore.initialize()` to return `list[int]` (the applied
versions).  This is backward-compatible: all existing callers discarded the
prior `None` return.

## Deliverables

- `handle_db_version()` and `handle_db_migrate()` in `foreman/cli.py`
- `db` subparser with `version` and `migrate` sub-commands in `build_parser()`
- `ForemanStore.initialize()` now returns `list[int]`
- 7 new tests in `DbCommandTests` in `tests/test_cli.py`

## Files changed

- `foreman/cli.py`
- `foreman/store.py`
- `tests/test_cli.py`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-29-db-migrate-cli.md`
- `docs/STATUS.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `CHANGELOG.md`

## Tests

- 7 new tests in `DbCommandTests`
- 203 non-E2E tests pass total; no regressions

## Risks

- `db migrate` calls `initialize()` which applies all pending migrations in one
  shot; there is no partial-apply mode — this is intentional per ADR-0005
- down-migration (`db rollback`) is not implemented; deferred until a real
  rollback scenario requires it

## Follow-ups

- define next slice from spec gaps or operator feedback
