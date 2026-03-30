# Current Sprint

- Sprint: `sprint-18-event-retention-pruning`
- Status: active
- Goal: implement spec-aligned pruning for old event rows without deleting
  history that still belongs to blocked or in-progress work
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/store.py`
  - `foreman/orchestrator.py`
  - `tests/test_store.py`
  - `tests/test_orchestrator.py`

## Included tasks

1. `[todo]` Add store support for spec-aligned event pruning
   Deliverable: the store can delete old events by project and cutoff while
   preserving events attached to blocked or in-progress tasks.

2. `[todo]` Run retention pruning from orchestrator startup
   Deliverable: project startup honors `event_retention_days` and emits
   `engine.event_pruned` when old events are removed.

3. `[todo]` Document retention behavior and operator expectations
   Deliverable: repo docs explain cutoff semantics, preserved-task exceptions,
   and what operators should expect when pruning runs.

## Excluded from this sprint

- multi-user dashboard concerns
- `foreman watch` live-tail alignment
- migration framework work
- backend auth and service-reachability health checks

## Acceptance criteria

- old events are pruned according to `event_retention_days`
- events for blocked or in-progress tasks are preserved regardless of age
- automated tests and docs make the retention boundary explicit for operators
