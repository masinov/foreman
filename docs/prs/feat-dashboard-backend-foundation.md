# PR Summary: feat-dashboard-backend-foundation

## Summary

- replace the raw stdlib dashboard server with a FastAPI backend
- preserve the current legacy dashboard shell and route surface on the new
  transport
- replan the dashboard sequence so React follows the backend foundation

## Scope

- add `foreman/dashboard_backend.py` for FastAPI routes, JSON responses, and
  SSE delivery
- convert `foreman/dashboard.py` into a legacy shell plus uvicorn entrypoint
- add FastAPI runtime dependencies in `pyproject.toml`
- strengthen dashboard tests around real ASGI endpoints
- archive sprint 22 and define sprint 23

## Files changed

- `pyproject.toml` — added FastAPI, uvicorn, and HTTP client dependencies
- `foreman/dashboard_backend.py` — new FastAPI dashboard backend
- `foreman/dashboard.py` — removed the raw stdlib handler and retained the
  legacy shell plus backend entrypoint
- `foreman/dashboard_api.py` — reused as the dashboard service layer behind
  the FastAPI routes
- `foreman/cli.py` — widened dashboard startup error handling for backend
  dependency failures
- `tests/test_dashboard.py` — added ASGI-backed HTTP route coverage and kept
  service-layer contract tests
- `README.md`, `docs/STATUS.md`, `docs/sprints/current.md`,
  `docs/sprints/backlog.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
  `docs/TESTING.md`, `docs/RELEASES.md`, and `CHANGELOG.md` — realigned repo
  memory around the backend-first sequence
- `docs/adr/ADR-0004-dashboard-backend-framework.md` — accepted FastAPI as the
  dashboard backend framework
- `docs/checkpoints/dashboard-backend-foundation.md` — recorded the backend
  foundation milestone
- `docs/sprints/archive/sprint-22-dashboard-backend-foundation.md` —
  archived the completed sprint
- `docs/prs/feat-dashboard-backend-foundation.md` — branch summary

## Migrations

- none

## Risks

- the legacy inline dashboard shell still exists and must be replaced by the
  React frontend
- the sprint SSE loop still polls SQLite directly inside the FastAPI stream
  generator
- the new web dependency stack is in place, but there is still no browser test
  suite

## Tests

- `./venv/bin/pip install -e . --no-build-isolation`
- `./venv/bin/python -m py_compile foreman/dashboard.py foreman/dashboard_api.py foreman/dashboard_backend.py foreman/cli.py tests/test_dashboard.py`
- `./venv/bin/python -m unittest tests.test_dashboard -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py foreman/dashboard.py foreman/dashboard_api.py foreman/dashboard_backend.py foreman/cli.py tests/test_dashboard.py`
- `./venv/bin/python -m unittest discover -s tests -v`

## Screenshots or output examples

- `foreman dashboard` now boots a uvicorn-backed FastAPI backend while still
  serving the transitional shell and current JSON plus SSE routes

## Acceptance criteria satisfied

- the dashboard now has a real backend framework instead of a raw stdlib HTTP
  handler
- the shipped dashboard routes still work on top of the new backend
- docs now make the backend-first sequence explicit before any React work

## Follow-ups

- implement `sprint-23-react-dashboard-foundation`
- decide whether the sprint SSE loop should move off direct SQLite polling
  after the frontend replacement lands
