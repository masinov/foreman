# Current Sprint

- Sprint: `sprint-24-product-surface-hardening`
- Status: active
- Goal: remove or finish placeholder product surfaces and strengthen product
  validation now that the dedicated dashboard frontend is in place
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/STATUS.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ROADMAP.md`
  - `foreman/cli.py`
  - `foreman/dashboard_runtime.py`
  - `foreman/dashboard_service.py`
  - `foreman/dashboard_backend.py`
  - `frontend/src/App.jsx`
  - `frontend/vite.config.js`
  - `scripts/dashboard_dev.py`
  - `tests/test_cli.py`
  - `tests/test_dashboard.py`

## Included tasks

1. `[done]` Remove or implement the remaining stub CLI product surfaces
   Deliverable: user-facing commands no longer fall through the generic
   placeholder handler where real product behavior is expected.

2. `[todo]` Close the most visible product-surface gaps after the dashboard
   frontend cutover
   Deliverable: the shipped dashboard and adjacent settings or CLI seams no
   longer leave obvious half-implemented flows in place.

3. `[todo]` Strengthen product-surface validation
   Deliverable: validation now covers the hardened CLI and dashboard paths
   above the current API and component-level checks.

4. `[done]` Clarify the dashboard runtime split and local development workflow
   Deliverable: runtime, service, and backend module roles are explicit and
   the React frontend can run in Vite dev mode against the FastAPI backend
   without relying on built assets.

## Excluded from this sprint

- schema migration framework work
- retention expansion beyond `events`
- autonomous task-selection mode
- authentication and multi-user concerns

## Acceptance criteria

- user-facing commands listed in the shipped CLI surface no longer depend on a
  generic stub fallback unless they fail explicitly as an intentional product
  boundary
- the dashboard and adjacent product seams no longer expose the most visible
  half-implemented flows left over from the bootstrap phase
- automated validation covers the hardened product paths beyond isolated API
  and component checks
