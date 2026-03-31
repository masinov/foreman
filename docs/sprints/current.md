# Current Sprint

- Sprint: `sprint-29-db-migrate-cli`
- Status: done
- Goal: add `foreman db migrate` and `foreman db version` CLI surfaces for
  operators to inspect schema version and apply pending migrations explicitly
- Primary references:
  - `docs/STATUS.md`
  - `foreman/store.py`
  - `foreman/migrations.py`
  - `foreman/cli.py`
  - `tests/test_cli.py`

## Included tasks

1. `[done]` Add `handle_db_version` and `handle_db_migrate` to `foreman/cli.py`
   Deliverable: `foreman db version` reports current schema version with
   a warning when `schema_migrations` is absent; `foreman db migrate` calls
   `store.initialize()` (idempotent), lists each applied migration by version
   and description, or confirms the schema is already up to date.

2. `[done]` Wire `db` subparser into `build_parser()`
   Deliverable: `foreman db --help`, `foreman db version --help`, and
   `foreman db migrate --help` all work; `--db` discovery applies to both
   sub-commands.

3. `[done]` Change `ForemanStore.initialize()` to return `list[int]`
   Deliverable: callers that ignored the prior `None` return are unaffected;
   `handle_db_migrate` uses the returned list to report what was applied.

4. `[done]` Write regression tests and update all repo-memory docs
   Deliverable: 7 new tests in `DbCommandTests`; STATUS, ARCHITECTURE, ROADMAP,
   CHANGELOG, current sprint, backlog, and archive written.

## Excluded from this sprint

- `db rollback` or down-migration path (deferred until a rollback scenario
  is observed in practice, per ADR-0005)

## Acceptance criteria

- `foreman db migrate --db <path>` on a fresh database applies all migrations
  and lists them
- running it again reports "already up to date"
- `foreman db version --db <path>` shows the current version after migration
- `foreman db version` on a database without `schema_migrations` prints a
  helpful message rather than crashing
- 7 new tests pass; full non-E2E suite (203 tests) passes with no regressions
