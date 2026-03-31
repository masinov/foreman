# React dashboard foundation

- Date: 2026-03-31
- Author: Foreman
- Status: completed
- Goal: replace the embedded dashboard shell with the dedicated frontend and
  keep the FastAPI backend as the durable product boundary
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/adr/ADR-0003-web-ui-api-boundary.md`
  - `docs/adr/ADR-0004-dashboard-backend-framework.md`
  - `frontend/`
  - `foreman/dashboard.py`
  - `foreman/dashboard_backend.py`
  - `tests/test_dashboard.py`

## Included tasks

1. `[done]` Create the dedicated frontend workspace
   Deliverable: a React and Vite app now owns dashboard rendering and client
   state.

2. `[done]` Replace the embedded Python-served UI
   Deliverable: product HTML, CSS, and browser logic are no longer embedded in
   `foreman/dashboard.py`.

3. `[done]` Add frontend-aware validation
   Deliverable: frontend component tests and bundle-build checks now sit
   alongside the existing dashboard API and FastAPI regression suite.

## Excluded from this checkpoint

- browser-driven end-to-end automation
- stub CLI removal and broader product-surface hardening
- schema migration work

## Acceptance criteria

- the product dashboard no longer depends on large inline HTML, CSS, and
  browser logic embedded inside Python modules
- the React frontend covers the shipped dashboard behavior without regressing
  the FastAPI backend contract
- automated validation now includes frontend-aware coverage beyond backend
  HTML-string assertions
