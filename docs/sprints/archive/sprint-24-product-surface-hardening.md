# Sprint Archive: sprint-24-product-surface-hardening

- Sprint: `sprint-24-product-surface-hardening`
- Status: completed
- Goal: remove or finish placeholder product surfaces and strengthen product
  validation now that the dedicated dashboard frontend is in place
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/STATUS.md`
  - `docs/ARCHITECTURE.md`
  - `foreman/cli.py`
  - `foreman/dashboard_runtime.py`
  - `foreman/dashboard_service.py`
  - `foreman/dashboard_backend.py`
  - `frontend/src/App.jsx`
  - `tests/test_cli.py`
  - `tests/test_dashboard.py`

## Final task statuses

1. `[done]` Remove or implement the remaining stub CLI product surfaces
   Deliverable: user-facing commands no longer fall through the generic
   `handle_stub` handler; project, sprint, task, run, and config commands are
   backed by real store and orchestrator integration.

2. `[done]` Close the most visible product-surface gaps after the dashboard
   frontend cutover
   Deliverable: the shipped dashboard now has a settings panel, sprint
   creation, and task creation backed by real FastAPI endpoints; `SettingsPanel`,
   `NewSprintModal`, and `NewTaskModal` React components wired into the app.

3. `[done]` Strengthen product-surface validation
   Deliverable: 15 new integration tests covering settings read/update, sprint
   creation, and task creation through both the service layer and FastAPI
   transport.

4. `[done]` Clarify the dashboard runtime split and local development workflow
   Deliverable: `foreman/dashboard_runtime.py` and `foreman/dashboard_service.py`
   roles are explicit; `foreman dashboard --dev` runs the React frontend against
   the FastAPI backend without requiring a production build;
   `scripts/dashboard_dev.py` provides a one-command dev loop.

## Deliverables

- `foreman/cli.py` — all shipped command surfaces implemented, `handle_stub`
  removed from the user-facing command path
- `foreman/dashboard_service.py` — settings read/update, sprint create, and
  task create endpoints
- `foreman/dashboard_backend.py` — FastAPI routes for the new product surfaces
- `frontend/src/App.jsx` — `SettingsPanel`, `NewSprintModal`, `NewTaskModal`
  components
- `tests/test_cli.py` — expanded subprocess coverage for hardened commands
- `tests/test_dashboard.py` — 15 new integration tests
- branch `feat/dashboard-settings-and-creation` merged to main

## Validation notes

- `./venv/bin/python -m pytest tests/ -x -q` — 152 pass, 3 frontend pass
- `npm --prefix frontend test`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-25-migration-framework-bootstrap`: introduce versioned SQLite schema
  migration support (bootstrap DDL is the remaining structural debt)
- `sprint-26-history-lifecycle-expansion`: extend retention to `runs` and
  stored prompts on top of the migration framework
