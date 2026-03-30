# Current Sprint

- Sprint: `sprint-20-migration-framework-bootstrap`
- Status: active
- Goal: introduce an explicit schema migration path for store evolution and
  retention-safe upgrades
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/store.py`
  - `tests/test_store.py`
  - `docs/ARCHITECTURE.md`
  - `docs/ROADMAP.md`

## Included tasks

1. `[todo]` Introduce explicit migration metadata and runner semantics
   Deliverable: the store has a versioned migration path instead of relying on
   bootstrap `CREATE TABLE IF NOT EXISTS` behavior alone.

2. `[todo]` Cover fresh initialization and upgrade behavior in tests
   Deliverable: automated tests prove both new-database initialization and at
   least one migration step from an older schema state.

3. `[todo]` Document migration and upgrade expectations
   Deliverable: repo docs explain how local `.foreman.db` upgrades are applied
   and what future slices should build on top of the migration boundary.

## Excluded from this sprint

- retention expansion beyond `events`
- backend auth and service-reachability health checks
- cross-project engine-instance configuration
- automatic sprint rebinding for long-lived `foreman watch` sessions

## Acceptance criteria

- the store uses an explicit migration boundary for schema evolution
- automated tests cover fresh initialization and upgrade behavior
- docs explain migration expectations clearly enough for operators and fresh
  agents
