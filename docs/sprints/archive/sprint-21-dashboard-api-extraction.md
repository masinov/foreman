# Sprint Archive: sprint-21-dashboard-api-extraction

- Sprint: `sprint-21-dashboard-api-extraction`
- Status: completed
- Goal: separate dashboard backend contracts from the embedded Python-served
  UI
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/STATUS.md`
  - `docs/adr/ADR-0003-web-ui-api-boundary.md`
  - `docs/ARCHITECTURE.md`
  - `foreman/dashboard.py`
  - `foreman/dashboard_api.py`
  - `tests/test_dashboard.py`

## Final task statuses

1. `[done]` Extract dashboard reads and actions into explicit API modules
   Deliverable: dashboard reads, actions, and streaming payloads now live in a
   dedicated backend API module instead of being assembled inline inside the
   request handler.

2. `[done]` Define stable API and streaming contracts for the frontend handoff
   Deliverable: JSON responses and incremental sprint-event stream envelopes
   are now tested directly at the extracted API boundary.

3. `[done]` Preserve current dashboard functionality behind the new API seam
   Deliverable: the legacy dashboard shell still serves project, sprint, task,
   activity, approve or deny, and human-message flows while routing through
   the extracted backend contract.

## Deliverables

- `foreman/dashboard_api.py` as the store-backed dashboard backend contract
- a thinner `DashboardHandler` that acts as an HTTP adapter instead of owning
  route data assembly
- dashboard tests shifted toward API-contract coverage rather than only
  reconstructing handler internals
- repo-memory rollover from API extraction to dashboard backend foundation

## Demo notes

- `./venv/bin/python -m unittest tests.test_dashboard -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-22-dashboard-backend-foundation`: replace the raw stdlib dashboard
  server with a real backend framework before the frontend rewrite
- `sprint-23-react-dashboard-foundation`: replace the legacy shell with a
  dedicated React frontend consuming the backend foundation
