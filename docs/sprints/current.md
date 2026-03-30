# Current Sprint

- Sprint: `sprint-22-react-dashboard-foundation`
- Status: active
- Goal: replace the legacy Python-served dashboard shell with a dedicated
  React frontend on top of the extracted backend API and streaming boundary
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/STATUS.md`
  - `docs/adr/ADR-0003-web-ui-api-boundary.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ROADMAP.md`
  - `foreman/dashboard.py`
  - `foreman/dashboard_api.py`
  - `tests/test_dashboard.py`

## Included tasks

1. `[todo]` Scaffold the dedicated frontend app and build pipeline
   Deliverable: the repo contains a maintainable React dashboard entrypoint
   instead of relying on substantial inline browser code inside Python.

2. `[todo]` Recreate the shipped dashboard surfaces on the new frontend
   Deliverable: project overview, sprint board, task detail, activity feed,
   human message input, and approve or deny flows all render through React
   while staying aligned to the mockup.

3. `[todo]` Wire the React client to the extracted JSON and streaming API
   Deliverable: the new frontend consumes the extracted dashboard API and
   sprint event stream without reading backend implementation details.

## Excluded from this sprint

- removing remaining stub CLI product commands
- schema migration framework work
- retention expansion beyond `events`
- autonomous task-selection mode
- authentication and multi-user concerns

## Acceptance criteria

- the product dashboard no longer depends on large inline HTML, CSS, and
  browser logic embedded inside Python modules
- the React frontend covers the currently shipped dashboard behaviors without
  regressing the extracted API contract
- automated validation includes frontend-aware coverage beyond backend-only
  HTML string checks
