# Current Sprint

- Sprint: `sprint-32-tier1-editing`
- Status: done
- Goal: Tier 1 polish — task field editing UI, sprint goal inline editing, and
  activity panel auto-scroll to bottom
- Branch: `feat/sprint-32-tier1-editing`
- Primary references:
  - `foreman/dashboard_service.py`
  - `foreman/dashboard_backend.py`
  - `frontend/src/App.jsx`
  - `frontend/src/components.jsx`
  - `frontend/src/api.js`
  - `frontend/src/styles.css`
  - `tests/test_dashboard.py`

## Included tasks

1. `[done]` Task field editing UI (title, task_type, acceptance_criteria)
   Deliverable: `TaskDetailDrawer` gains an edit mode (✎ button → edit state).
   In edit mode: title becomes an `<input>`, task_type becomes a chip selector,
   acceptance_criteria becomes a `<textarea>`; Save/Cancel buttons apply or
   discard. `update_task_fields()` extended from `{description, priority}` to
   `{title, task_type, acceptance_criteria, description, priority}` with full
   validation. `PATCH /api/tasks/{id}` and `updateTask` in api.js already
   existed; `handleSaveTask` added to App.jsx.

2. `[done]` Sprint goal inline editing
   Deliverable: Sprint view header goal line shows a ✎ button; clicking it
   opens an inline input with Save/Cancel. New `update_sprint_fields()` service
   method accepts `{title, goal}`; `PATCH /api/sprints/{id}` routes to
   `update_sprint_fields` when `status` key is absent, to `transition_sprint`
   when `status` is present. `updateSprint` added to api.js.
   `handleUpdateSprintGoal` added to App.jsx.

3. `[done]` Activity panel auto-scroll to bottom
   Deliverable: `EventList` accepts `containerRef` and `onScroll` props, wired
   to the `.activity-stream` scroll container. `atActivityBottomRef` tracks
   whether the user is at the bottom; `useLayoutEffect` auto-scrolls on each
   events update when the user was already at the bottom.

4. `[done]` 11 new tests in `DashboardTaskEditingTests`

## Acceptance criteria

- `PATCH /api/tasks/{id}` with `{title, task_type, acceptance_criteria}` updates
  those fields; rejects empty title and unknown task_type
- `PATCH /api/sprints/{id}` with `{goal: "..."}` updates goal and returns 200
- `PATCH /api/sprints/{id}` with `{status: "completed"}` still transitions sprint
- `PATCH /api/sprints/{id}` with `{}` returns 400
- 63 non-E2E dashboard tests pass; 20 E2E tests pass
