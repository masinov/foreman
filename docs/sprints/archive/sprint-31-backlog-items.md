# Sprint 31: Backlog clearance

- Sprint: `sprint-31-backlog-items`
- Status: done
- Branch: `feat/sprint-31-backlog-items`
- Goal: clear the five items that accumulated in the sprint-30 backlog

## Summary

All five backlog items shipped end-to-end: service layer, FastAPI transport,
API client, and React frontend.

**Sprint creation with inline tasks** — `NewSprintModal` gains a task-entry
row with a text input, Add button (Enter shortcut), and a removable pending
list. The `create_sprint` service method and `POST /api/projects/{id}/sprints`
both accept an optional `initial_tasks` list. Tasks are created atomically with
the sprint; the response includes `tasks_created`.

**Task cancellation** — `cancel_task()` sets status to `cancelled` and rejects
tasks already in `done` or `cancelled` with 400. `POST /api/tasks/{id}/cancel`
wired in the backend. The task detail drawer shows a "Cancel task" button for
all non-terminal tasks; on success the drawer closes and the board refreshes.

**Task dependencies display** — `depends_on_task_ids` added to the `get_task()`
response. The detail drawer renders a Dependencies section with `.dep-chip`
elements resolved against the current sprint's `taskIndex`; unresolved IDs fall
back to the raw task ID.

**Event log load-more** — `store.list_sprint_events()` gained a `before_event_id`
cursor path (DESC query, result reversed to ASC). The service `list_sprint_events()`
supports `before_event_id` and now returns `has_more` on all responses.
`GET /api/sprints/{id}/events` accepts a `before` query parameter. The activity
panel in `App.jsx` renders a "Load older events" button above the event list
when `has_more` is true; clicking it prepends the older batch.

**Cancelled sprint filter** — "Cancelled" added to `STATUS_FILTER_OPTIONS` in
`SprintList`. The kanban board's Done column now also includes cancelled sprints.

## Deliverables

- Extended `store.list_sprint_events()` with `before_event_id` cursor
- Extended `DashboardService.list_sprint_events()` with `before_event_id` +
  `has_more` flag on all responses
- `DashboardService.cancel_task()` + `POST /api/tasks/{id}/cancel`
- Extended `DashboardService.create_sprint()` with `initial_tasks`
- `POST /api/sprints/{id}/sprints` accepts and validates `initial_tasks`
- `GET /api/sprints/{id}/events` accepts `before` query parameter
- `depends_on_task_ids` in `get_task()` response
- `cancelTask()` and extended `listSprintEvents()` / `createSprint()` in `api.js`
- `handleCancelTask`, `handleLoadMoreEvents`, `handleCreateSprint` update in
  `App.jsx`; `hasMoreEvents` / `isLoadingMoreEvents` state; taskIndex + onCancel
  passed to `TaskDetailDrawer`
- Updated `NewSprintModal` with inline task entry in `components.jsx`
- Cancel task button and Dependencies section in `TaskDetailDrawer`
- Cancelled option in `STATUS_FILTER_OPTIONS`; kanban Done includes cancelled
- CSS: `.dep-chip`, `.btn-cancel-task`, `.load-more-btn`, `.task-entry-row`,
  `.pending-tasks`, `.pending-task-item`, `.pending-task-remove`
- 8 new tests in `DashboardSprintTaskBacklogTests`

## Files changed

- `foreman/store.py`
- `foreman/dashboard_service.py`
- `foreman/dashboard_backend.py`
- `frontend/src/App.jsx`
- `frontend/src/api.js`
- `frontend/src/components.jsx`
- `frontend/src/styles.css`
- `foreman/dashboard_frontend_dist/` (rebuilt)
- `tests/test_dashboard.py`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-31-backlog-items.md`
- `docs/STATUS.md`

## Tests

- 8 new tests in `DashboardSprintTaskBacklogTests`
- 221 non-E2E tests pass; 20 E2E tests pass; no regressions

## Risks

- Cancelled tasks disappear from the board immediately (STATUS_COLUMNS does not
  include `cancelled`); a cancelled task can only be seen by navigating to the
  task detail directly or loading it from a prior event reference.
- `depends_on_task_ids` is display-only; the orchestrator does not yet enforce
  dependency ordering when selecting the next task.

## Follow-ups

- Task editing UI (title, type, acceptance criteria from the dashboard)
- Sprint goal editing after creation
- Activity panel scroll-to-bottom affordance
