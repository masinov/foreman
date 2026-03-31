# ADR-0005: Schema Migration Strategy

- Status: accepted
- Date: 2026-03-31
- Deciders: engine team

## Context

The Foreman SQLite store has been growing incrementally through bootstrap DDL
(`CREATE TABLE IF NOT EXISTS`).  That approach is safe only during the initial
build phase: once production databases exist, any structural change — adding a
column, adding an index, renaming a table — must be applied to the live
database without data loss.

Without a migration framework:

- schema changes silently fail on existing stores that already have the table,
- there is no record of when a schema change was applied or which version a
  given database is at,
- retention and history expansion (sprint-26) would require manual ALTER TABLE
  statements with no automated path.

The store needs an explicit, version-tracked migration mechanism before
sprint-26 adds new columns to the `runs` and `events` tables.

## Decision

Introduce a zero-dependency, store-native migration framework:

1. **`foreman/migrations.py`** owns an ordered list of migration tuples:
   `(version: int, description: str, sql: str)`.  Versions are consecutive
   integers starting at 1.  Migration 1 is the current baseline schema.
   Future schema changes are appended as new entries.

2. **`schema_migrations` table** (created before any other schema work) records
   which migration versions have been applied and when.

3. **`ForemanStore.initialize()`** creates the `schema_migrations` table then
   calls `migrate()`.  It remains safe to call multiple times.

4. **`ForemanStore.migrate()`** applies any unapplied migrations in version
   order, records each application in `schema_migrations`, and returns the list
   of newly applied version numbers.  Calling it on an up-to-date database is a
   no-op.

5. **`ForemanStore.schema_version()`** returns the highest applied version, or
   0 if no migrations have been applied yet.

No external library (Alembic, yoyo-migrations, etc.) is introduced.  SQLite's
`executescript` handles multi-statement migrations.

## Consequences

### Positive

- Any future schema change is expressed as an appended migration entry; the
  runner applies it automatically on the next `initialize()` call.
- Existing databases are upgraded without data loss.
- `schema_version()` gives operators and tests a reliable way to inspect the
  schema state of any store.
- The migration list is append-only and self-documenting.

### Negative / Trade-offs

- The baseline schema is now defined twice: once in migration 1 and once as
  prose in ADR history.  The migration list is authoritative.
- `executescript` implicitly commits any open transaction.  Multi-statement
  migrations must be written so that partial application leaves the database in
  a safe state (this is consistent with SQLite's own transaction semantics for
  DDL).
- Rollback of a migration requires a separate migration entry rather than a
  built-in down path.  This is acceptable for the current product scope.

## Alternatives Considered

- **Continue with `CREATE TABLE IF NOT EXISTS`**: ruled out because it cannot
  add columns to existing tables without data loss.
- **Alembic**: adds a substantial external dependency and Python packaging
  complexity for a single-file SQLite use case.
- **Manual migration scripts**: no automated path, no version tracking,
  error-prone for operators.

## Implementation Notes

- `SCHEMA_SQL` has been removed from `store.py`; migration 1 in
  `migrations.py` is the single source of truth for the baseline schema.
- All existing store tests continue to pass because `initialize()` delegates to
  `migrate()`, which applies migration 1 on a fresh database exactly as the old
  `executescript(SCHEMA_SQL)` did.
- The `test_partial_db_upgraded_to_latest` test is currently skipped (only one
  migration exists); it will activate automatically when migration 2 is added
  in sprint-26.
