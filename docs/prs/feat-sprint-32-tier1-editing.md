# PR: feat/sprint-32-tier1-editing

## Summary

- Task field editing in `TaskDetailDrawer`: ✎ button → edit mode with inline
  title input, task-type chip selector, and acceptance-criteria textarea;
  Save/Cancel buttons call `PATCH /api/tasks/{id}`
- Sprint goal inline editing: ✎ button in sprint header → inline input with
  Save/Cancel; new `update_sprint_fields` backend method; `PATCH
  /api/sprints/{id}` routes to field updates when `status` key is absent
- Activity panel auto-scroll: scroll position tracked on `.activity-stream`;
  `useLayoutEffect` scrolls to bottom on new events when user is already there

## Scope

Backend service, FastAPI endpoint, React frontend (App + components + styles),
unit tests. No schema changes, no migrations.

## Files changed

| File | Change |
|------|--------|
| `foreman/dashboard_service.py` | Extended `update_task_fields`; new `update_sprint_fields`; empty-body guard |
| `foreman/dashboard_backend.py` | Dual-routing `PATCH /api/sprints/{id}` |
| `frontend/src/api.js` | Added `updateSprint` |
| `frontend/src/App.jsx` | `handleSaveTask`, `handleUpdateSprintGoal`, goal edit state, scroll tracking |
| `frontend/src/components.jsx` | `TaskDetailDrawer` edit mode; `EventList` containerRef/onScroll |
| `frontend/src/styles.css` | Editing UI and sprint goal input styles |
| `tests/test_dashboard.py` | `DashboardTaskEditingTests` (11 tests) |
| `foreman/dashboard_frontend_dist/` | Rebuilt |
| `docs/sprints/current.md` | Updated to sprint-32 |
| `docs/sprints/archive/sprint-32-tier1-editing.md` | Created |

## Migrations

None.

## Risks

- `PATCH /api/sprints/{id}` now accepts `{goal: ...}` in addition to
  `{status: ...}`. The routing key is presence of `status`. Unknown fields
  return 400 from `update_sprint_fields`.

## Tests

- 63 dashboard tests pass
- 20 E2E tests pass

## Acceptance criteria satisfied

- Task title, type, criteria editable in drawer
- Sprint goal editable inline in header
- Activity panel auto-scrolls on new events when at bottom
- All prior tests pass

## Follow-ups

Tier 2 and Tier 3 gaps remain (see `project_backlog_tiers.md` memory file).
