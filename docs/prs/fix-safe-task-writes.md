# PR Summary: fix/safe-task-writes

## Summary

- Sprint 56 slice 1. What an operator does to a task while the engine is
  working on it now takes effect.

## Scope

- `ForemanStore.update_task_engine_state`: workflow-state columns only,
  `WHERE status != 'cancelled'`.
- `ForemanOrchestrator._save_task` replaces all 29 whole-row task writes;
  `_adopt_operator_changes` and a status check run before every step;
  `TaskCancelledError` unwinds a workflow and settles its open run.

## Files changed

- `foreman/store.py`, `foreman/orchestrator.py`, `tests/test_orchestrator.py`
- `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- Any engine code path that relied on rewriting a task's title, type or
  criteria through `save_task` no longer does so, except the autonomous
  `signal.task_started` path, which opts in explicitly.
- One extra task read per workflow step.

## Tests

- `python -m unittest discover -s tests`: 1038 pass, 1 skipped (3 new)
- `ruff check foreman tests scripts`: clean

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A task cancelled mid-step stays cancelled, keeps the operator's edit, has
  no running run or lease left, and its commit is not on `main`.
- An edit made mid-step survives the engine's next write.
- A blocker signal followed by a completion marker leaves the task blocked.

## Follow-ups

- Slice 2: crash-safe steps.
