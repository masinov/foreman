# Current Sprint

- Sprint: `sprint-31-backlog-items`
- Status: done
- Goal: clear the sprint-30 backlog — sprint creation with inline tasks, task
  cancellation, task dependencies display, event log load-more pagination, and
  sprint status filter for cancelled sprints
- Branch: `feat/sprint-31-backlog-items`
- Primary references:
  - `foreman/store.py`
  - `foreman/dashboard_service.py`
  - `foreman/dashboard_backend.py`
  - `frontend/src/App.jsx`
  - `frontend/src/components.jsx`
  - `frontend/src/api.js`
  - `frontend/src/styles.css`
  - `tests/test_dashboard.py`

## Included tasks

1. `[done]` Sprint creation with inline task entry
   Deliverable: `NewSprintModal` has a task-entry row (input + Add button, Enter
   shortcut, removable pending list); `create_sprint` service and
   `POST /api/projects/{id}/sprints` accept `initial_tasks`; tasks are created
   atomically with the sprint and reported in `tasks_created`.

2. `[done]` Task cancellation
   Deliverable: `cancel_task()` service method + `POST /api/tasks/{id}/cancel`;
   rejects done/already-cancelled tasks with 400; Cancel task button in
   `TaskDetailDrawer` for non-terminal tasks; cancelled task deselected and board
   refreshed.

3. `[done]` Task dependencies display
   Deliverable: `depends_on_task_ids` added to `get_task()` response;
   `TaskDetailDrawer` shows a Dependencies section with dep-chip elements
   resolved against the current sprint's taskIndex.

4. `[done]` Event log load-more pagination
   Deliverable: `store.list_sprint_events()` extended with `before_event_id`
   cursor (DESC query, reversed to ASC); service `list_sprint_events()` supports
   `before_event_id` and now returns `has_more` flag on all responses;
   `GET /api/sprints/{id}/events` accepts `before` query param; frontend shows
   "Load older events" button at top of activity panel when `has_more` is true.

5. `[done]` Sprint status filter for cancelled
   Deliverable: "Cancelled" filter added to `STATUS_FILTER_OPTIONS` in
   `SprintList`; kanban board's Done column now includes cancelled sprints.

6. `[done]` 8 new tests in `DashboardSprintTaskBacklogTests`

## Acceptance criteria

- `POST /api/projects/{id}/sprints` with `initial_tasks` creates tasks and
  returns `tasks_created` count
- `POST /api/tasks/{id}/cancel` marks task cancelled; returns 400 for done tasks
- `GET /api/tasks/{id}` returns `depends_on_task_ids`
- `GET /api/sprints/{id}/events?before=X` returns events older than X in
  display order
- `GET /api/sprints/{id}/events?limit=N` returns `has_more: true` when there
  are more than N events
- 221 non-E2E tests pass; 20 E2E tests pass
