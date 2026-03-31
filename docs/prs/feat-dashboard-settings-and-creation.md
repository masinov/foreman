# PR Summary: feat-dashboard-settings-and-creation

## Summary

- Closes the most visible product-surface gaps after the dashboard frontend
  cutover by adding a settings panel, sprint creation, and task creation
  backed by real FastAPI endpoints and the dashboard service layer.
- Strengthens product-surface validation with 15 new integration tests.

## Scope

- Settings: project settings read/update through a new service method and
  FastAPI endpoint pair, with validation for unknown top-level keys and
  nested settings type checks.
- Sprint creation: service method generating stable slug-based IDs, FastAPI
  endpoint, and a React modal with title/goal fields.
- Task creation: service method with type validation, FastAPI endpoint, and a
  React modal with title/type/acceptance-criteria fields.
- Frontend: `SettingsPanel`, `NewSprintModal`, `NewTaskModal` components,
  topbar gear icon, sprint toolbar "+ New sprint" button, sprint header
  "+ New task" button.
- All new flows are wired end-to-end: React component -> api.js -> FastAPI
  endpoint -> dashboard service -> SQLite store.

## Files changed

- `foreman/dashboard_service.py` — added `get_project_settings`,
  `update_project_settings`, `create_sprint`, `create_task`, `_stable_slug`
  helper, `DashboardValidationError` exception
- `foreman/dashboard_backend.py` — added 4 FastAPI endpoints for settings,
  sprint creation, and task creation
- `frontend/src/components.jsx` — added `SettingsPanel`, `SettingsToggle`,
  `NewSprintModal`, `NewTaskModal`; updated `Topbar` and `SprintList`
- `frontend/src/App.jsx` — added state, handlers, and rendering for settings,
  sprint creation, and task creation flows
- `frontend/src/api.js` — added `getProjectSettings`,
  `updateProjectSettings`, `createSprint`, `createTask` methods
- `frontend/src/styles.css` — added settings panel, toggle switch, form,
  modal, and action button styles
- `tests/test_dashboard.py` — added `DashboardSettingsTests` class with 15
  integration tests
- `foreman/dashboard_frontend_dist/` — rebuilt frontend assets

## Migrations

- none

## Risks

- The committed dashboard build output must stay in sync with frontend source.
- Settings validation currently allows arbitrary keys inside the nested
  `settings` dict; a later slice may want to constrain these.

## Tests

- 15 new integration tests in `DashboardSettingsTests`:
  - GET/PATCH project settings via HTTP
  - settings validation (unknown fields, non-dict settings, 404s)
  - sprint creation (success, empty title, 404)
  - task creation (success, empty title, invalid type, 404)
  - service layer stable ID generation and settings validation
- All 152 Python tests pass, 3 frontend tests pass, frontend builds clean.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Sprint task 2: settings panel, sprint creation, and task creation are backed
  by real FastAPI endpoints with full React integration.
- Sprint task 3: 15 new integration tests cover the hardened product paths
  through both service and transport layers.

## Follow-ups

- browser-driven end-to-end dashboard validation
- constrain nested settings keys in `update_project_settings`
- implement `task_selection_mode="autonomous"` in the orchestrator
