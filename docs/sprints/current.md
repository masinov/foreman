# Current Sprint

- Sprint: `sprint-21-dashboard-api-extraction`
- Status: active
- Goal: replace the embedded dashboard delivery path with an explicit backend
  API boundary for a dedicated React frontend
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/STATUS.md`
  - `docs/adr/ADR-0003-web-ui-api-boundary.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ROADMAP.md`
  - `foreman/dashboard.py`
  - `tests/test_dashboard.py`

## Included tasks

1. `[todo]` Extract dashboard reads and actions into explicit API modules
   Deliverable: dashboard routes and streaming no longer depend on embedded UI
   markup living inside the same backend module.

2. `[todo]` Define stable API and streaming contracts for the frontend handoff
   Deliverable: JSON and incremental event responses are documented and
   covered well enough for a React frontend to consume without reading Python
   implementation details.

3. `[todo]` Preserve current dashboard functionality behind the new API seam
   Deliverable: existing project, sprint, task, activity, approve or deny, and
   human-message flows continue to work while the UI delivery path is decoupled.

## Excluded from this sprint

- building the React app itself
- schema migration framework work
- retention expansion beyond `events`
- autonomous task-selection mode
- cross-project engine-instance configuration

## Acceptance criteria

- dashboard backend routes are separated cleanly enough that the UI can move
  to a dedicated frontend without carrying inline HTML along with it
- automated tests cover the extracted API and streaming contracts
- docs explain the backend/frontend split clearly enough for the next sprint
  to build the React dashboard without re-litigating architecture
