# PR Summary: refactor-dashboard-runtime-dev-workflow

## Summary

- rename the confusing dashboard runtime and service modules so the file tree
  matches the actual architecture
- add an explicit frontend-dev mode for the FastAPI backend plus Vite `/api`
  proxying
- add a one-command local dashboard development launcher for frontend and
  backend work
- remove the remaining shipped CLI placeholder flows by implementing the
  project, sprint, task, run, and config commands directly

## Scope

- replace `foreman/dashboard.py` with `foreman/dashboard_runtime.py`
- replace `foreman/dashboard_api.py` with `foreman/dashboard_service.py`
- keep `foreman/dashboard_backend.py` as the FastAPI transport layer while
  adding frontend-dev redirect behavior
- extend `foreman dashboard` with frontend-mode and reload options for local
  development
- add `scripts/dashboard_dev.py` and `npm --prefix frontend run dev:full`
- replace the remaining `handle_stub` product-surface calls in `foreman/cli.py`
- update tests and live docs to the new module names, workflow, and hardened
  CLI surface

## Files changed

- `foreman/dashboard_runtime.py` — runtime entrypoint, asset helpers, and
  frontend-dev launch support
- `foreman/dashboard_service.py` — store-backed dashboard service layer
- `foreman/dashboard_backend.py` — FastAPI transport updated for frontend-dev
  redirects and reload-safe app factory use
- `foreman/cli.py` — dashboard CLI wiring for `--frontend-mode`,
  `--frontend-dev-url`, and `--reload`, plus real project, sprint, task, run,
  and config command handling
- `scripts/dashboard_dev.py` — combined local backend and Vite launcher
- `frontend/package.json`, `frontend/vite.config.js` — Vite proxying and
  one-command dev workflow
- `tests/test_dashboard.py`, `tests/test_cli.py` — coverage for the renamed
  modules, frontend-dev redirect path, dev-runner help surface, and the
  hardened CLI product commands
- `README.md`, `docs/STATUS.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
  `docs/TESTING.md`, ADRs 0002-0004, and related sprint or release docs —
  aligned live repo memory

## Migrations

- none

## Risks

- the frontend dev workflow still assumes a local Node toolchain with `npm`
  available in `PATH`
- backend reload mode now works through environment-backed uvicorn factory
  startup, which is correct but adds a little runtime indirection
- browser-driven end-to-end validation is still missing even though the local
  dev loop is now sane
- `task_selection_mode="autonomous"` is still an explicit product boundary, so
  the new `foreman run` command hard-fails outside directed-selection projects

## Tests

- `./venv/bin/python -m py_compile foreman/cli.py foreman/dashboard_runtime.py foreman/dashboard_backend.py foreman/dashboard_service.py scripts/dashboard_dev.py tests/test_dashboard.py tests/test_cli.py`
- `./venv/bin/python -m unittest tests.test_dashboard tests.test_cli -v`
- `npm --prefix frontend test`

## Screenshots or output examples

- `npm --prefix frontend run dev:full` starts the FastAPI backend on
  `http://127.0.0.1:8080` and the Vite frontend on
  `http://127.0.0.1:5173/dashboard`

## Acceptance criteria satisfied

- the dashboard runtime, service, and FastAPI backend roles are now explicit
  from the module names alone
- local frontend development no longer depends on prebuilt assets or manual
  API origin rewiring
- the shipped CLI no longer exposes placeholder handlers for project, sprint,
  task, run, or config commands
- validation covers the new dashboard dev-mode redirect path and the
  developer-facing launcher surfaces

## Follow-ups

- continue `sprint-24-product-surface-hardening` with the remaining
  dashboard-adjacent gaps and stronger browser-level validation
