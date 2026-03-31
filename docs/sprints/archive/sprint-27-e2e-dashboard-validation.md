# Sprint Archive: sprint-27-e2e-dashboard-validation

- Sprint: `sprint-27-e2e-dashboard-validation`
- Status: completed
- Goal: add browser-driven end-to-end validation of the Foreman dashboard
  through a real Chromium browser against a live FastAPI server and seeded
  SQLite database
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `foreman/dashboard_backend.py`
  - `frontend/src/App.jsx`
  - `frontend/src/components.jsx`
  - `tests/test_e2e.py`

## Final task statuses

1. `[done]` Install Playwright and pytest-playwright
   Deliverable: `playwright` and `pytest-playwright` in venv; Chromium browser
   binaries installed; `pyproject.toml` `[project.optional-dependencies] e2e`
   group added.

2. `[done]` Write live-server fixture
   Deliverable: `live_dashboard_url` starts a uvicorn dashboard server with a
   seeded test DB; skips gracefully if Playwright or built assets are missing.

3. `[done]` Write E2E tests covering key dashboard flows
   Deliverable: 20 Playwright tests in `tests/test_e2e.py`:
   - `TestDashboardLoad` (3): page renders, project visible, FOREMAN logo visible
   - `TestProjectNavigation` (3): project → sprint list, sprint → board columns,
     board shows seeded task cards
   - `TestTaskDetail` (4): card click opens drawer, title visible, acceptance
     criteria visible, close button dismisses drawer
   - `TestSettingsPanel` (4): settings opens, workflow field visible, edit
     reveals Save button, save clears footer
   - `TestNewSprint` (3): modal opens, Create disabled without title, sprint
     appears after creation
   - `TestNewTask` (3): modal opens, Create disabled without title, task appears
     after creation

## Deliverables

- `tests/test_e2e.py` — 20 E2E tests, session-scoped live server fixture
- `pyproject.toml` — `e2e` optional dependency group
- branch `feat/e2e-dashboard-validation` merged to main

## Validation notes

- `./venv/bin/python -m pytest tests/test_e2e.py -v` — 20 passed
- `./venv/bin/python -m pytest tests/ -x -q` — 208 passed
- `./venv/bin/python scripts/validate_repo_memory.py` — passed

## Follow-ups moved forward

- `task_selection_mode="autonomous"` orchestrator implementation
- `foreman db migrate` CLI surface for schema inspection
