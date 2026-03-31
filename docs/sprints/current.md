# Current Sprint

- Sprint: `sprint-27-e2e-dashboard-validation`
- Status: done
- Goal: add browser-driven end-to-end validation of the Foreman dashboard,
  exercising the full stack through a real Chromium browser against a live
  FastAPI server and seeded SQLite database
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/STATUS.md`
  - `foreman/dashboard_backend.py`
  - `frontend/src/App.jsx`
  - `frontend/src/components.jsx`
  - `tests/test_e2e.py`

## Included tasks

1. `[done]` Install Playwright and pytest-playwright; install Chromium binaries
   Deliverable: `playwright` and `pytest-playwright` available in the venv;
   Chromium browser binaries installed; `pyproject.toml` records the `e2e`
   optional dependency group.

2. `[done]` Write live-server pytest fixture
   Deliverable: `live_dashboard_url` session-scoped fixture starts a real
   uvicorn server with a seeded SQLite database and waits for it to accept
   connections; skips gracefully if Playwright or built frontend assets are
   absent.

3. `[done]` Write E2E test suite
   Deliverable: 20 Playwright tests in `tests/test_e2e.py` covering dashboard
   load, project navigation, sprint board, task detail drawer, settings panel
   (open, field change, save), new sprint modal (open, disabled state, create),
   and new task modal (open, disabled state, create).

## Excluded from this sprint

- `task_selection_mode="autonomous"` orchestrator implementation
- `foreman db migrate` CLI surface

## Acceptance criteria

- 20 E2E tests pass against the full stack: Chromium → FastAPI → SQLite
- E2E tests skip cleanly when Playwright is not installed
- full pytest suite (208 tests) passes with no regressions
