# Dashboard slice

- Date: 2026-03-30
- Author: Foreman
- Status: active
- Goal: build the first interactive dashboard slice aligned to the mockup
  using persisted Foreman project, sprint, task, run, and event state
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/adr/ADR-0001-runner-session-backend-contract.md`
  - `foreman/store.py`
  - `foreman/dashboard.py`
  - `foreman/cli.py`

## Included tasks

 1. `[done]` Add the first dashboard shell for project overview and sprint board
   Deliverable: a runnable UI entrypoint renders project overview and active
   sprint board data from persisted SQLite-backed state.

2. `[in_progress]` Surface task detail and recent activity in the dashboard
   Deliverable: selecting a task reveals branch, role, status, token, and
   recent event context aligned to the mockup's board and activity hierarchy.

3. `[todo]` Define the first dashboard data-access boundary
   Deliverable: the UI reuses SQLite-backed read models or thin projections
   instead of hardcoded mock data, and the chosen boundary is documented in
   repo memory.

## Excluded from this sprint

  - authentication and multi-user concerns
  - live streaming transport beyond polling or snapshot semantics
  - task-creation and settings modals beyond placeholders
  - multi-project dashboard polish

## Acceptance criteria
  - a user can load a dashboard surface that matches the mockup hierarchy for
   project overview, sprint board, and activity feed
  - dashboard data comes from current persisted Foreman state rather than
   hardcoded demo data
  - dashboard behavior that depends on runner or approval semantics cites
   `ADR-0001`
  - docs and validation remain good enough for a fresh autonomous agent to pick
   the next slice without extra human context
