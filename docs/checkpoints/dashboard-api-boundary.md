# Dashboard API boundary

- Date: 2026-03-31
- Author: Foreman
- Status: completed
- Goal: extract the first durable backend contract for the product dashboard
  before replacing the legacy Python-served shell with a dedicated frontend
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/adr/ADR-0003-web-ui-api-boundary.md`
  - `foreman/dashboard.py`
  - `foreman/dashboard_api.py`
  - `tests/test_dashboard.py`

## Included tasks

1. `[done]` Separate dashboard reads, actions, and streaming payload assembly
   from the inline legacy shell
   Deliverable: `foreman/dashboard_api.py` now exposes store-backed JSON and
   streaming payload contracts.

2. `[done]` Reduce the dashboard request handler to a transport adapter
   Deliverable: `DashboardHandler` now delegates to the extracted backend API
   instead of assembling response payloads inline.

3. `[done]` Lock the contract down with direct tests
   Deliverable: dashboard regression coverage now exercises the extracted API
   boundary and SSE payload shape directly.

## Excluded from this checkpoint

- replacing the inline shell with the dedicated React frontend
- frontend build, component, or browser-test infrastructure
- migration framework work or broader product-surface hardening

## Acceptance criteria

- the backend contract for the product dashboard exists independently from the
  inline UI delivery path
- the next sprint can build a React frontend without reverse-engineering
  handler internals
- repo memory reflects that the legacy shell is transitional, not the target
  architecture
