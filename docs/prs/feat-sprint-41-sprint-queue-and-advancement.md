# PR: feat/sprint-41-sprint-queue-and-advancement

## Summary

- Wired the orchestrator sprint advancement loop to `autonomy_level`: autonomous
  mode auto-activates the next planned sprint and continues; supervised/directed
  modes stop and emit `engine.sprint_ready` for human re-start.
- Added `get_next_planned_sprint` to `ForemanStore`.
- `start_agent` auto-activates the first planned sprint when none is active;
  returns a validation error if no sprints exist at all.
- Replaced the kanban/filter project view with a two-row queue-focused layout:
  Next Up + Active (top row), Queue + Archive (bottom row).
- Removed the Start/Promote-to-active button; queue order is the intent signal.

## Scope

Engine sprint lifecycle, store, dashboard service, frontend project view.

## Files changed

- `foreman/orchestrator.py` — `_sprint_fully_resolved`, `_advance_sprint`,
  `_emit_sprint_event`, restructured `run_project` advancement loop
- `foreman/store.py` — `get_next_planned_sprint`
- `foreman/dashboard_service.py` — `start_agent` auto-activation
- `frontend/src/components.jsx` — two-row layout, removed kanban, removed
  Start/Promote-to-active, removed filter toolbar
- `frontend/src/styles.css` — new `pq-*` layout CSS, removed `sk-*` kanban CSS
- `frontend/src/App.jsx` — added `"top"` direction to `handleReorderSprint`
- `tests/test_orchestrator.py` — `SprintAdvancementTests` class (8 tests),
  fixed workflow_step assertions to filter out `_builtin:orchestrator` runs
- `tests/test_dashboard.py` — updated start_agent test, added no-sprints test
- `docs/sprints/current.md` — sprint marked done

## Migrations

None. No schema changes.

## Risks

- Four pre-existing test failures in `test_orchestrator.py` (workflow step
  ordering in shipped-workflow tests). Confirmed present on `main` before this
  branch — not introduced here.
- `engine.sprint_ready` event type is new; `getEventCategory` in the frontend
  may render it as unknown in the activity stream (non-blocking).

## Tests

```
./venv/bin/python -m pytest tests/test_orchestrator.py tests/test_dashboard.py -q
# 157 passed, 4 pre-existing failures
```

## Acceptance criteria satisfied

- Orchestrator reads `autonomy_level` and auto-advances in autonomous mode.
- Supervised/directed modes stop after sprint completion and wait for Run.
- `start_agent` auto-activates first planned sprint when none is active.
- Project view uses the two-row serial-queue layout.
- No kanban view, no Start/Promote-to-active button.
- Archive zone collapsible, defaults to collapsed.

## Follow-ups

- Fix `engine.sprint_ready` in `getEventCategory` frontend handler.
- Fix the 4 pre-existing `test_run_project_advances_one_task_through_the_shipped_workflow`
  family failures.
- Manual validation: create 3 planned sprints, test all three autonomy levels.
