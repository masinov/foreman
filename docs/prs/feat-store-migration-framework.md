# PR: feat/store-migration-framework

## Summary

Introduces a zero-dependency, version-tracked schema migration framework for
the Foreman SQLite store.  The bootstrap `CREATE TABLE IF NOT EXISTS` DDL is
replaced by an ordered `MIGRATIONS` list in `foreman/migrations.py`.
`ForemanStore.initialize()` now creates a `schema_migrations` tracking table
and applies any unapplied migrations in order; calling it multiple times is a
no-op.

## Scope

- `foreman/migrations.py` — new module owning the append-only `MIGRATIONS`
  list; migration 1 is the current baseline schema
- `foreman/store.py` — removed `SCHEMA_SQL`; added `_SCHEMA_MIGRATIONS_DDL`,
  `ForemanStore.migrate()`, `ForemanStore.schema_version()`; updated
  `initialize()`
- `tests/test_migrations.py` — 17 new tests
- `docs/adr/ADR-0005-schema-migration-strategy.md` — accepted ADR
- `docs/sprints/current.md`, `docs/STATUS.md`, `CHANGELOG.md` — sprint and
  repo memory updated

## Files changed

| File | Change |
|------|--------|
| `foreman/migrations.py` | new |
| `foreman/store.py` | modified |
| `tests/test_migrations.py` | new |
| `docs/adr/ADR-0005-schema-migration-strategy.md` | new |
| `docs/sprints/current.md` | replaced (sprint-24 → sprint-25, done) |
| `docs/STATUS.md` | updated |
| `CHANGELOG.md` | updated |

## Migrations

No data migrations.  Migration 1 is functionally identical to the old
`SCHEMA_SQL` baseline; existing stores opened after this change will have
migration 1 recorded in their new `schema_migrations` table after the first
call to `initialize()`.

## Risks

- `executescript` in Python's `sqlite3` module commits any open transaction
  implicitly; migration SQL must be DDL-only or safe to replay.  Current
  migration 1 uses `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`
  which satisfies this.
- Partial application of a migration (e.g. process killed mid-script) leaves
  the version unrecorded; re-running `migrate()` will re-apply the migration.
  SQLite DDL inside `IF NOT EXISTS` guards is safe to replay.

## Tests

```
./venv/bin/python -m pytest tests/test_migrations.py -v
# 16 passed, 1 skipped

./venv/bin/python -m pytest tests/ -x -q
# 168 passed, 1 skipped
```

The skipped test (`test_partial_db_upgraded_to_latest`) requires ≥ 2
migrations; it will activate automatically when migration 2 lands in sprint-26.

## Acceptance criteria satisfied

- `initialize()` on a fresh DB produces a schema functionally identical to the
  old bootstrap path ✓
- `initialize()` and `migrate()` on an up-to-date DB are no-ops ✓
- `schema_version()` returns the correct highest-applied version ✓
- all 168 tests pass ✓

## Follow-ups

- sprint-26: add migration 2 for `runs` or `events` retention column(s); the
  `test_partial_db_upgraded_to_latest` test will activate and validate the
  incremental upgrade path end to end
- consider a `foreman db migrate` CLI surface for operators to inspect and
  apply migrations explicitly
