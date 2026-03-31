# PR: feat/db-migrate-cli

## Summary

- Adds `foreman db version` and `foreman db migrate` CLI surfaces
- `db version` shows current schema version; handles missing `schema_migrations`
  gracefully for pre-migration-framework databases
- `db migrate` applies pending migrations via `store.initialize()`, reports
  applied versions with descriptions, or confirms the schema is up to date
- `ForemanStore.initialize()` now returns `list[int]` (backward-compatible)

## Scope

- `foreman/cli.py`: `handle_db_version`, `handle_db_migrate`, `db` subparser
- `foreman/store.py`: `initialize()` return type `None` → `list[int]`
- `tests/test_cli.py`: `DbCommandTests` (7 tests)
- Repo-memory: STATUS, ARCHITECTURE, ROADMAP, CHANGELOG, sprints

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
- `docs/prs/feat-db-migrate-cli.md`

## Migrations

None (this sprint adds CLI tooling for managing migrations, not new migrations).

## Risks

- `initialize()` return-type change is backward-compatible; no existing callers
  used the return value.

## Tests

- 7 new tests; 203 non-E2E tests pass total

## Acceptance criteria satisfied

- Fresh DB: `db migrate` applies and lists all migrations
- Re-run: `db migrate` reports already up to date
- `db version` shows correct version after migration
- `db version` on uninitialized DB shows zero and helpful message
- Full non-E2E suite passes with no regressions
