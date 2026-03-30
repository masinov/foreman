# PR Summary: feat-event-retention-pruning

## Summary

- add spec-aligned pruning for old project events
- preserve event history for blocked and in-progress tasks
- roll repo memory forward from retention pruning to watch live-tail
  alignment

## Scope

- add a store API for deleting old events by project and cutoff
- run pruning from orchestrator startup when `event_retention_days` is set
- emit `engine.event_pruned` through a synthetic orchestrator run
- add store and orchestrator coverage for pruning and preserved-task behavior
- archive sprint 18 and define sprint 19

## Files changed

- `foreman/store.py` — added project-scoped event pruning with
  blocked/in-progress preservation
- `foreman/orchestrator.py` — added startup retention pruning and synthetic
  pruning event emission
- `tests/test_store.py` — added pruning coverage for protected and unprotected
  task histories
- `tests/test_orchestrator.py` — added startup pruning coverage with durable
  `engine.event_pruned` assertions
- `README.md`, `docs/STATUS.md`, `docs/sprints/current.md`,
  `docs/sprints/backlog.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
  `docs/TESTING.md`, `docs/RELEASES.md`, `CHANGELOG.md` — aligned repo memory
  to the completed slice
- `docs/sprints/archive/sprint-18-event-retention-pruning.md` — archived the
  completed sprint
- `docs/prs/feat-event-retention-pruning.md` — branch summary

## Migrations

- none

## Risks

- retention currently applies only to `events`; `runs` rows and stored prompts
  still accumulate
- `engine.event_pruned` must currently attach to a task-bound synthetic run
  because the schema does not support pure project-level events
- `foreman watch` still relies on bounded polling snapshots

## Tests

- `./venv/bin/python -m py_compile foreman/store.py foreman/orchestrator.py tests/test_store.py tests/test_orchestrator.py`
- `./venv/bin/python -m unittest tests.test_store.ForemanStoreTests.test_prune_old_events_preserves_blocked_and_in_progress_task_history tests.test_orchestrator.ForemanOrchestratorTests.test_run_project_prunes_old_done_task_events_and_preserves_blocked_history -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- old events are pruned according to `event_retention_days`
- events for blocked or in-progress tasks are preserved regardless of age
- automated tests and docs make the retention boundary explicit for operators

## Follow-ups

- implement `sprint-19-watch-live-tail-alignment`
- decide whether retention should later extend beyond `events`
