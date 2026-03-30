# Sprint Archive: sprint-18-event-retention-pruning

- Sprint: `sprint-18-event-retention-pruning`
- Status: completed
- Goal: implement spec-aligned pruning for old event rows without deleting
  history that still belongs to blocked or in-progress work
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/store.py`
  - `foreman/orchestrator.py`
  - `tests/test_store.py`
  - `tests/test_orchestrator.py`

## Final task statuses

1. `[done]` Add store support for spec-aligned event pruning
   Deliverable: the store now deletes old project events by cutoff while
   preserving events attached to blocked and in-progress tasks.

2. `[done]` Run retention pruning from orchestrator startup
   Deliverable: project startup now honors `event_retention_days` and emits
   `engine.event_pruned` when old events are removed.

3. `[done]` Document retention behavior and operator expectations
   Deliverable: repo docs now explain cutoff semantics, preserved-task
   exceptions, and the current boundary that only `events` are pruned.

## Deliverables

- store-level event pruning by project and cutoff
- orchestrator startup retention hook driven by `event_retention_days`
- active-work preservation for blocked and in-progress task history
- durable `engine.event_pruned` records through synthetic orchestrator runs
- repo-memory rollover from event retention pruning to watch live-tail
  alignment

## Demo notes

- `./venv/bin/python -m unittest tests.test_store.ForemanStoreTests.test_prune_old_events_preserves_blocked_and_in_progress_task_history tests.test_orchestrator.ForemanOrchestratorTests.test_run_project_prunes_old_done_task_events_and_preserves_blocked_history -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-19-watch-live-tail-alignment`: align `foreman watch` with the
  dashboard live transport and the spec's live-tail intent
- `sprint-20-migration-framework-bootstrap`: introduce an explicit schema
  migration path for future store evolution
