# Dashboard backend foundation

- Date: 2026-03-31
- Author: Foreman
- Status: completed
- Goal: establish a real product backend for the dashboard before proceeding
  with the dedicated frontend rewrite
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/adr/ADR-0003-web-ui-api-boundary.md`
  - `docs/adr/ADR-0004-dashboard-backend-framework.md`
  - `foreman/dashboard.py`
  - `foreman/dashboard_api.py`
  - `foreman/dashboard_backend.py`
  - `tests/test_dashboard.py`

## Included tasks

1. `[done]` Replace the raw dashboard server with a real backend framework
   Deliverable: FastAPI and uvicorn now own dashboard HTTP delivery.

2. `[done]` Preserve the current dashboard route surface on the new backend
   Deliverable: the transitional shell, JSON routes, and SSE path continue to
   work on top of the FastAPI app.

3. `[done]` Add backend-facing HTTP tests
   Deliverable: dashboard tests now exercise the ASGI app directly instead of
   only testing service methods and HTML strings.

## Excluded from this checkpoint

- replacing the transitional shell with the dedicated React frontend
- browser automation or frontend component infrastructure
- migration framework work or broader product-surface hardening

## Acceptance criteria

- the dashboard no longer depends on a raw stdlib server for product delivery
- the backend foundation is explicit enough for the React rewrite to build on
- repo memory reflects that the backend comes before the dedicated frontend
