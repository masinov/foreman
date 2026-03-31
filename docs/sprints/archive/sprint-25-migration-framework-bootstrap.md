# Sprint Archive: sprint-25-migration-framework-bootstrap

- Sprint: `sprint-25-migration-framework-bootstrap`
- Status: completed
- Goal: introduce an explicit schema migration path for store evolution and
  retention-safe upgrades
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/store.py`
  - `foreman/migrations.py`
  - `tests/test_migrations.py`

## Final task statuses

1. `[done]` Introduce `foreman/migrations.py` with an ordered `MIGRATIONS` list
   Deliverable: baseline schema expressed as migration 1; list enforces
   consecutive integer versions starting at 1.

2. `[done]` Replace bootstrap DDL in `store.py` with a migration runner
   Deliverable: `ForemanStore.initialize()` creates the `schema_migrations`
   tracking table then delegates to `migrate()`; `migrate()` applies any
   unapplied migrations in order, records each in `schema_migrations`, and
   returns the list of newly-applied version numbers; calling either on an
   up-to-date database is a no-op.

3. `[done]` Add `ForemanStore.schema_version()`
   Deliverable: returns the highest applied migration version, or 0 on a
   never-migrated database.

4. `[done]` Add `tests/test_migrations.py`
   Deliverable: 17 tests covering list integrity, fresh install, idempotency on
   in-memory and file databases, incremental upgrade from a
   partially-migrated store, and schema version accuracy.

5. `[done]` Write `docs/adr/ADR-0005-schema-migration-strategy.md`
   Deliverable: accepted ADR documents the append-only list, tracking table,
   zero-external-dependency design decision, and trade-offs.

## Deliverables

- `foreman/migrations.py` — new module; single source of truth for schema history
- `foreman/store.py` — `SCHEMA_SQL` removed; `_SCHEMA_MIGRATIONS_DDL`,
  `ForemanStore.migrate()`, `ForemanStore.schema_version()` added;
  `initialize()` updated
- `tests/test_migrations.py` — 17 tests (16 pass, 1 skips until migration 2 exists)
- `docs/adr/ADR-0005-schema-migration-strategy.md` — accepted ADR
- branch `feat/store-migration-framework` merged to main

## Validation notes

- `./venv/bin/python -m pytest tests/test_migrations.py -v` — 16 passed, 1 skipped
- `./venv/bin/python -m pytest tests/ -x -q` — 168 passed, 1 skipped
- `./venv/bin/python scripts/validate_repo_memory.py` — passed

## Notes

The skipped test (`test_partial_db_upgraded_to_latest`) requires at least 2
migrations to exercise the incremental upgrade path. It will activate
automatically when migration 2 is added in sprint-26 with no changes to the
test itself.

## Follow-ups moved forward

- `sprint-26-history-lifecycle-expansion`: add migration 2 for `runs`/`events`
  retention columns; the dormant incremental-upgrade test activates and
  validates end to end
- consider a `foreman db migrate` CLI surface for operators to inspect schema
  version and apply pending migrations explicitly
