# Sprint Archive: sprint-10-dashboard-implementation

- Sprint: `sprint-10-dashboard-implementation`
- Status: completed
- Goal: build the first interactive dashboard slice aligned to the mockup
  using persisted Foreman project, sprint, task, run, and event state
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/adr/ADR-0001-runner-session-backend-contract.md`
  - `docs/adr/ADR-0002-dashboard-data-access-boundary.md`
  - `foreman/dashboard.py`
  - `foreman/cli.py`

## Final task statuses

1. `[done]` Add the first dashboard shell for project overview and sprint board
   Deliverable: a runnable UI entrypoint renders project overview and active
   sprint board data from persisted SQLite-backed state.

2. `[done]` Surface task detail and recent activity in the dashboard
   Deliverable: selecting a task reveals branch, role, status, token, and
   recent event context aligned to the mockup's board and activity hierarchy.

3. `[done]` Define the first dashboard data-access boundary
   Deliverable: the UI reuses SQLite-backed read models or thin projections
   instead of hardcoded mock data, and the chosen boundary is documented in
   repo memory.

## Deliverables

- `foreman.dashboard` with an HTTP server, embedded dashboard HTML shell, and
  JSON API endpoints for projects, sprints, tasks, and events
- `foreman dashboard --db <path>` CLI command
- task detail overlay with run history, acceptance criteria, and step visit
  counts
- accepted `ADR-0002-dashboard-data-access-boundary`
- dashboard unit coverage in `tests/test_dashboard.py`
- repo-memory rollover from dashboard implementation to dashboard polish

## Demo notes

- `./venv/bin/python -m unittest tests.test_dashboard -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/foreman dashboard --help`

## Follow-ups moved forward

- `sprint-11-multi-project-dashboard-polish`: add human message input,
  activity filtering, and multi-project navigation
- backlog: streaming transport for dashboard, security review workflow
  variant, event-retention pruning, optional PR or checkpoint automation, and
  dashboard approve or deny integration
