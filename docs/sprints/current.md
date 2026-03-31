# Current Sprint

- Sprint: `sprint-25-migration-framework-bootstrap`
- Status: done
- Goal: introduce an explicit schema migration path for store evolution and
  retention-safe upgrades
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/store.py`
  - `foreman/migrations.py`
  - `tests/test_migrations.py`

## Included tasks

1. `[done]` Introduce `foreman/migrations.py` with an ordered
   `MIGRATIONS` list that owns the full schema history.
   Deliverable: baseline schema expressed as migration 1; list enforces
   consecutive versions starting at 1.

2. `[done]` Replace bootstrap DDL in `store.py` with a migration runner.
   Deliverable: `ForemanStore.initialize()` creates the `schema_migrations`
   tracking table then calls `migrate()`; `migrate()` applies any unapplied
   migrations in order and records each in `schema_migrations`; calling either
   method on an already-up-to-date database is a no-op.

3. `[done]` Add `ForemanStore.schema_version()`.
   Deliverable: returns the highest applied migration version, or 0 for a
   database that has never been migrated.

4. `[done]` Add `tests/test_migrations.py` with full migration framework coverage.
   Deliverable: 17 tests covering list integrity, fresh install, idempotency on
   in-memory and file databases, incremental upgrade from a partially-migrated
   store, and schema version accuracy.

5. `[done]` Write `docs/adr/ADR-0005-schema-migration-strategy.md`.
   Deliverable: accepted ADR documents the append-only list, tracking table,
   and the zero-external-dependency design decision.

## Excluded from this sprint

- actual new columns or table changes (those land in sprint-26 on top of this
  framework)
- retention expansion beyond `events`
- autonomous task-selection mode
- authentication and multi-user concerns

## Acceptance criteria

- `ForemanStore.initialize()` on a fresh database produces a schema that is
  functionally identical to the old bootstrap DDL path
- calling `initialize()` or `migrate()` multiple times on the same database is
  a no-op with no duplicate rows or errors
- `schema_version()` returns the correct highest-applied version
- all 168 tests pass (16 new migration tests, existing 152 unchanged)
- `test_partial_db_upgraded_to_latest` activates automatically when a second
  migration is added in sprint-26
