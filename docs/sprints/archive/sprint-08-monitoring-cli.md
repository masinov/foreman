# Sprint Archive: sprint-08-monitoring-cli

- Sprint: `sprint-08-monitoring-cli`
- Status: completed
- Goal: expose active Foreman state through CLI board, history, watch, and
  cost surfaces without opening SQLite manually
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Final task statuses

1. `[done]` Add `foreman board --db <path>` for current sprint task inspection
   Deliverable: operators can list active sprint tasks grouped by status with
   task type, branch, assigned role, blocked reason, and token context.

2. `[done]` Add `foreman history --db <path>` and `foreman cost --db <path>`
   for run and event inspection
   Deliverable: operators can inspect recent task history plus persisted cost
   and token summaries from SQLite without manual queries.

3. `[done]` Add `foreman watch --db <path>` as a polling activity snapshot
   Deliverable: the CLI can refresh task counts and recent activity in a
   mockup-aligned monitoring view suitable for terminal use.

## Deliverables

- store-backed `foreman board`, `foreman history`, `foreman cost`, and
  `foreman watch` handlers in `foreman.cli`
- monitoring read-model helpers in `foreman.store` for aggregate run totals,
  per-task rollups, sprint-scoped task counts, and recent activity slices
- CLI subprocess coverage for board, history, cost, project watch, and
  run-scoped watch
- store coverage for sprint-scoped monitoring reads and recent event ordering
- repo-memory rollover from the monitoring CLI sprint to the runner ADR sprint

## Demo notes

- `./venv/bin/python -m unittest tests.test_store tests.test_cli -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/foreman board --help`
- `./venv/bin/foreman history --help`
- `./venv/bin/foreman cost --help`
- `./venv/bin/foreman watch --help`

## Follow-ups moved forward

- `sprint-09-runner-session-backend-adr`: capture the first accepted ADR for
  runner sessions, approval policy, and backend contract boundaries
- backlog: dashboard implementation, security review workflow variant,
  optional PR or checkpoint automation, event-retention pruning, and
  multi-project dashboard polish
