# ADR-0003: Web UI And API Boundary

## Status

Accepted

## Context

Foreman originally shipped a dashboard surface from one Python module as
embedded HTML, CSS, and browser JavaScript served by the backend itself.

That implementation was fast to land, but it creates structural problems:

1. backend transport, API logic, and UI rendering are coupled in one module,
2. there is no dedicated frontend codebase or build pipeline,
3. browser behavior is difficult to test as a real product surface,
4. future dashboard work risks deepening a shape we already know is wrong for
   a production product.

The mockup in `docs/mockups/foreman-mockup-v6.html` is authoritative for UI
hierarchy and interaction intent, but it does not define the implementation
stack.

We need an explicit product boundary that supports a durable web UI.

## Decision

Foreman's product web UI will use a **dedicated React frontend** that consumes
an explicit Python backend API.

The boundary is:

- backend code owns persistence, orchestration, and API or streaming transport,
- frontend code owns HTML rendering, client state, and interaction behavior,
- the dashboard API exposes JSON and incremental event streaming contracts,
- substantial product UI markup must not live as embedded strings inside
  backend Python modules.

That original monolithic implementation is now treated as transitional debt
that has been removed, not as a baseline to extend indefinitely.

## Consequences

### Positive

- separates product UI concerns from backend transport and orchestration
- makes React-based UI development, testing, and iteration possible
- creates a stable contract for frontend and backend evolution
- reduces the risk that future UI work gets trapped in a bootstrap-only shape

### Negative

- introduces a real frontend codebase and build workflow
- requires API extraction before the current UI can be replaced cleanly
- increases short-term refactor cost before additional dashboard features land

## Follow-through requirements

- extract dashboard reads, actions, and streaming into explicit backend API
  modules before building the new frontend
- keep the mockup as the interaction and hierarchy reference during the React
  rewrite
- add API contract tests and frontend-focused validation as part of the
  dashboard replacement work

## References

- `docs/mockups/foreman-mockup-v6.html`
- `foreman/dashboard_runtime.py`
- `foreman/dashboard_service.py`
- `foreman/dashboard_backend.py`
- `docs/ARCHITECTURE.md`
- `docs/STATUS.md`
