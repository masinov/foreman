# refactor/store-package

## Summary

Sprint 57 slice 3. `foreman/store.py` becomes the package `foreman/store/`.

## Scope

- `base.py`: `StoreBase` (connection, `_write`, migrations, schema repair),
  SQL helpers, `MigrationError`, `retried_on_lock`.
- `rows.py`: row-to-model functions and JSON helpers.
- One module per aggregate, each a `StoreBase` subclass holding that
  aggregate's methods, text-exact: `ProjectStore`, `SprintStore`,
  `TaskStore`, `RunStore`, `EventStore`, `GateStore`, `MetaSessionStore`,
  `LeaseStore`, `EngineCommandStore`, `ApiTokenStore`, `NotificationStore`.
- `ForemanStore` inherits all of them. Every caller keeps
  `from foreman.store import ForemanStore` and the same methods.
- `retried_on_lock` on the 20 methods that open their own
  `with self._connection` transaction, sharing `_write`'s backoff.

## Files changed

`foreman/store.py` removed; `foreman/store/` (14 modules) added;
`tests/test_store_safety.py` (one import, one new test); changelog, sprint.

## Migrations

None.

## Risks

- A decorated method is replayed whole after a lock error. Each holds exactly
  one transaction (checked by script over the AST), so nothing is applied
  twice.
- The parts are joined by inheritance, not composition: they share one
  connection and call each other through `self` (a task save assigns a key
  from the project). Splitting them into objects that take a connection is
  possible later without changing callers.

## Tests

Full Python suite (1065 tests) and `ruff check`.

## Acceptance criteria satisfied

Slice 3 as written in `docs/sprints/current.md`.

## Follow-ups

Store concurrency tests beyond the lock retry (slice 8).
