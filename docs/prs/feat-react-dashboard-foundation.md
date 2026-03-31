# PR Summary: feat-react-dashboard-foundation

## Summary

- replace the embedded dashboard shell with a dedicated React and Vite
  frontend
- serve the built frontend assets from the FastAPI dashboard backend while
  preserving the existing JSON and SSE contract
- roll repo memory forward from dashboard foundation to product-surface
  hardening

## Scope

- add a dedicated frontend workspace under `frontend/`
- move dashboard rendering and client state into React
- reduce `foreman/dashboard.py` to asset guarding and the uvicorn entrypoint
- update `foreman/dashboard_backend.py` to serve built frontend assets plus
  the extracted API contract
- split dashboard validation across Python API tests and frontend component
  tests
- archive sprint 23 and define sprint 24

## Files changed

- `frontend/package.json`, `frontend/vite.config.js`, `frontend/index.html`,
  `frontend/src/*` — new React dashboard workspace, styling, routing, API
  client, and component tests
- `foreman/dashboard.py` — removed embedded product markup and kept only the
  dashboard runtime entrypoint and asset checks
- `foreman/dashboard_backend.py` — serves the built frontend shell and assets
  alongside the JSON and SSE API routes
- `foreman/dashboard_frontend_dist/*` — built frontend assets committed for
  runtime delivery
- `tests/test_dashboard.py` — updated dashboard coverage around built frontend
  delivery and the preserved backend contract
- `pyproject.toml`, `.gitignore` — package data and frontend workspace support
- `README.md`, `docs/STATUS.md`, `docs/sprints/current.md`,
  `docs/sprints/backlog.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
  `docs/TESTING.md`, `docs/RELEASES.md`, `CHANGELOG.md` — aligned repo memory
  to the completed slice
- `docs/sprints/archive/sprint-23-react-dashboard-foundation.md` — archived
  the completed sprint
- `docs/checkpoints/react-dashboard-foundation.md` — recorded the dedicated
  frontend checkpoint
- `docs/prs/feat-react-dashboard-foundation.md` — branch summary

## Migrations

- none

## Risks

- the dashboard still lacks browser-driven end-to-end coverage
- the committed build output in `foreman/dashboard_frontend_dist/` must stay
  synchronized with the source app in `frontend/`
- the SSE transport still polls SQLite inside the FastAPI stream loop

## Tests

- `npm --prefix frontend test`
- `npm --prefix frontend run build`
- `./venv/bin/python -m py_compile foreman/dashboard.py foreman/dashboard_backend.py foreman/dashboard_api.py tests/test_dashboard.py`
- `./venv/bin/python -m unittest tests.test_dashboard -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py foreman/dashboard.py foreman/dashboard_backend.py foreman/dashboard_api.py tests/test_dashboard.py`
- `./venv/bin/pip install -e . --no-build-isolation`
- `./venv/bin/python -m unittest discover -s tests -v`

## Screenshots or output examples

- `foreman dashboard` now serves the dedicated React frontend at
  `/dashboard` and keeps the existing `/api/...` and `/api/sprints/.../stream`
  backend contract intact

## Acceptance criteria satisfied

- the product dashboard no longer depends on large inline HTML, CSS, and
  browser logic embedded inside Python modules
- the React frontend now covers the shipped dashboard behaviors on top of the
  FastAPI backend contract
- automated validation includes frontend-aware coverage beyond backend HTML
  assertions

## Follow-ups

- implement `sprint-24-product-surface-hardening`
- decide whether to add browser-driven end-to-end coverage before or during
  the hardening sprint
- revisit whether committed built assets should later be generated as part of
  a release pipeline instead of staying checked in permanently
