# PR Summary: refactor-dashboard-api-extraction

## Summary

- extract the dashboard backend contract into a dedicated API module
- reduce the legacy dashboard handler to an HTTP adapter over that contract
- roll repo memory forward from API extraction to the dashboard backend
  foundation

## Scope

- add `foreman/dashboard_api.py` for dashboard reads, actions, and streaming
  payload assembly
- rework `foreman/dashboard.py` so request handling delegates to the extracted
  API contract
- strengthen dashboard tests around the extracted API and SSE payload shape
- archive sprint 21 and define sprint 22

## Files changed

- `foreman/dashboard_api.py` — new store-backed dashboard API contract
- `foreman/dashboard.py` — reduced the legacy dashboard shell to an HTTP
  adapter plus inline transitional markup
- `tests/test_dashboard.py` — shifted coverage toward the extracted API
  contract and action behavior
- `README.md`, `docs/STATUS.md`, `docs/sprints/current.md`,
  `docs/sprints/backlog.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
  `docs/TESTING.md`, `docs/RELEASES.md`, `CHANGELOG.md` — aligned repo memory
  to the completed slice
- `docs/sprints/archive/sprint-21-dashboard-api-extraction.md` — archived the
  completed sprint
- `docs/checkpoints/dashboard-api-boundary.md` — recorded the first extracted
  dashboard API boundary checkpoint
- `docs/prs/refactor-dashboard-api-extraction.md` — branch summary

## Migrations

- none

## Risks

- the legacy dashboard shell still ships large inline HTML, CSS, and browser
  logic from `foreman/dashboard.py`
- dashboard live transport still polls SQLite inside the threaded SSE loop
- there is still no dedicated frontend build, component, or end-to-end browser
  test stack

## Tests

- `./venv/bin/python -m py_compile foreman/dashboard.py foreman/dashboard_api.py tests/test_dashboard.py`
- `./venv/bin/python -m unittest tests.test_dashboard -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py foreman/dashboard.py foreman/dashboard_api.py tests/test_dashboard.py`
- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/python -m unittest discover -s tests -v`

## Screenshots or output examples

- the legacy dashboard still loads at `foreman dashboard`, but its routes now
  resolve through the extracted backend API contract

## Acceptance criteria satisfied

- dashboard backend reads, actions, and stream payloads are separated from the
  inline UI shell
- automated tests cover the extracted API and streaming contract directly
- docs now describe the backend or frontend split clearly enough for sprint 22

## Follow-ups

- implement `sprint-22-dashboard-backend-foundation`
- implement `sprint-23-react-dashboard-foundation`
- decide whether the sprint SSE loop should stay on direct SQLite polling or
  move to a separate transport mechanism after the React frontend lands
