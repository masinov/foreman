# Sprint Archive: sprint-23-react-dashboard-foundation

- Sprint: `sprint-23-react-dashboard-foundation`
- Status: completed
- Goal: replace the legacy inline dashboard shell with a dedicated React
  frontend on top of the FastAPI backend and extracted dashboard service layer
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/STATUS.md`
  - `docs/adr/ADR-0003-web-ui-api-boundary.md`
  - `docs/adr/ADR-0004-dashboard-backend-framework.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ROADMAP.md`
  - `frontend/`
  - `foreman/dashboard.py`
  - `foreman/dashboard_backend.py`
  - `tests/test_dashboard.py`

## Final task statuses

1. `[done]` Scaffold the dedicated frontend app and build pipeline
   Deliverable: the repo now contains a maintainable React and Vite dashboard
   entrypoint instead of substantial inline browser code inside Python.

2. `[done]` Recreate the shipped dashboard surfaces on the new frontend
   Deliverable: project overview, sprint board, task detail, activity feed,
   human message input, and approve or deny flows now render through React
   while staying aligned to the mockup.

3. `[done]` Wire the React client to the FastAPI backend and streaming path
   Deliverable: the frontend now consumes the extracted dashboard service and
   FastAPI transport without reading backend implementation details.

## Deliverables

- `frontend/` as the dedicated React and Vite dashboard workspace
- `foreman/dashboard_frontend_dist/` as the built frontend output served by
  the backend
- `foreman/dashboard_backend.py` updated to serve the built frontend plus the
  existing JSON and SSE dashboard contract
- `foreman/dashboard.py` reduced to the uvicorn entrypoint and frontend asset
  guard
- dashboard coverage split across `tests/test_dashboard.py` and
  `frontend/src/App.test.jsx`
- repo-memory rollover from React dashboard foundation to product-surface
  hardening

## Demo notes

- `npm --prefix frontend test`
- `npm --prefix frontend run build`
- `./venv/bin/python -m unittest tests.test_dashboard -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-24-product-surface-hardening`: remove or implement remaining stub
  CLI surfaces and strengthen product-surface validation
- `sprint-25-migration-framework-bootstrap`: introduce versioned SQLite schema
  migration support
