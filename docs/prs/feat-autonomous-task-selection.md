# PR: feat/autonomous-task-selection

## Summary

- Implements `task_selection_mode="autonomous"` in `ForemanOrchestrator`
- `select_next_task()` dispatches to `_select_next_task_autonomous()` for
  autonomous projects; resumes in-progress tasks first, then creates placeholder
  tasks up to the per-sprint `max_autonomous_tasks` limit (default 5)
- Placeholder tasks are persisted to SQLite with `created_by="orchestrator"`;
  the agent populates them via the existing `signal.task_started` handler

## Scope

- `foreman/orchestrator.py`: new `_select_next_task_autonomous()`, updated
  `select_next_task()` dispatch
- `tests/test_orchestrator.py`: `AutonomousTaskSelectionTests` (8 tests)
- Repo-memory: STATUS, ARCHITECTURE, ROADMAP, CHANGELOG, sprints

## Files changed

- `foreman/orchestrator.py`
- `tests/test_orchestrator.py`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-28-autonomous-task-selection.md`
- `docs/STATUS.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `CHANGELOG.md`
- `docs/prs/feat-autonomous-task-selection.md`

## Migrations

None.

## Risks

- Agent must emit `signal.task_started` to populate placeholders; gap is
  documented in STATUS.md.
- `max_autonomous_tasks` counts all orchestrator-created tasks in the sprint
  (including done ones), bounding total autonomous work rather than concurrency.

## Tests

- 8 new unit tests; 204 non-E2E tests pass total

## Acceptance criteria satisfied

- `select_next_task()` returns a placeholder for an autonomous project with no
  in-progress task
- In-progress task is resumed before a new placeholder is created
- Limit enforced: `None` returned when limit reached
- Directed mode and unknown-mode error unchanged
- Full non-E2E suite passes with no regressions
