# Current Sprint

- Sprint: `sprint-30-wire-dead-surfaces`
- Status: done
- Goal: wire the most visible dead surfaces — Stop agent button, sprint lifecycle
  transitions, task field exposure (description, priority), and complete run
  serialization
- Branch: `feat/sprint-30-wire-dead-surfaces`
- Primary references:
  - `foreman/dashboard_service.py`
  - `foreman/dashboard_backend.py`
  - `frontend/src/App.jsx`
  - `frontend/src/components.jsx`
  - `frontend/src/api.js`
  - `tests/test_dashboard.py`
  - `tests/test_e2e.py`

## Included tasks

1. `[done]` Add `transition_sprint()` to `DashboardService` and
   `PATCH /api/sprints/{sprint_id}` to the FastAPI backend
   Deliverable: planned→active, active→completed/cancelled transitions persist
   `started_at`/`completed_at` and reject invalid paths with 400.

2. `[done]` Add `update_task_fields()` to `DashboardService` and
   `PATCH /api/tasks/{task_id}` to the FastAPI backend
   Deliverable: `description` and `priority` can be updated through the API;
   unknown fields are rejected with 400.

3. `[done]` Add `stop_agent()` to `DashboardService` and
   `POST /api/projects/{project_id}/agent/stop` to the FastAPI backend
   Deliverable: marks all in-progress tasks in the active sprint as blocked,
   emits `human.stop_requested` events, returns count of affected tasks.

4. `[done]` Extend run serialization in `get_task()` to include `session_id`,
   `branch_name`, `started_at`, `completed_at`
   Deliverable: run detail payload exposes all four fields; test confirms values
   round-trip correctly.

5. `[done]` Expose `description` and `priority` in `get_task()` and
   `list_sprint_tasks()` responses
   Deliverable: task detail drawer shows description section and priority field
   when non-default values are present.

6. `[done]` Wire Stop agent button `onClick` in `App.jsx`
   Deliverable: clicking Stop agent calls `POST /api/projects/{id}/agent/stop`
   and refreshes state; button is disabled during pending actions.

7. `[done]` Add sprint status badge + transition buttons in sprint view header
   Deliverable: sprint view header shows current status badge; planned sprints
   show "Start sprint"; active sprints show "Complete sprint".

8. `[done]` Add lifecycle action buttons to sprint list cards in `SprintList`
   Deliverable: each sprint card in the list view shows Start/Complete/Cancel
   buttons depending on current status; kanban board cards do the same.

9. `[done]` Fix E2E test regressions from previous session's dashboard overhaul
   Deliverable: `test_sprint_card_navigates_to_board` scoped to `.col-title`
   to avoid strict-mode collision with `detail-status` span;
   `test_task_detail_shows_title` updated from `.detail-title` to `h2`.

10. `[done]` Add 10 new tests in `DashboardSprintLifecycleTests`; full non-E2E
    suite is 213 tests; E2E suite is 20 tests.

## Acceptance criteria

- `PATCH /api/sprints/{id}` with `{"status":"active"}` on a planned sprint
  returns 200 with `started_at` set
- `PATCH /api/sprints/{id}` with an invalid transition returns 400
- `PATCH /api/tasks/{id}` with `{"description":"...","priority":2}` returns
  updated task detail
- `PATCH /api/tasks/{id}` with `{"status":"done"}` returns 400
- `POST /api/projects/{id}/agent/stop` with an in-progress task returns
  `stopped: 1`; task is blocked; `human.stop_requested` event is persisted
- `GET /api/tasks/{id}` returns `session_id`, `branch_name`, `started_at`,
  `completed_at` on run objects
- Stop agent button in sprint header has working `onClick`; disabled while action
  is pending
- Sprint header shows current status badge; planned sprint shows "Start sprint"
  button; active sprint shows "Complete sprint" button
- Sprint list cards show Start/Complete/Cancel action buttons per status
- 213 non-E2E tests pass; 20 E2E tests pass
