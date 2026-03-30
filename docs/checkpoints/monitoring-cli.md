# Checkpoint: monitoring-cli

## What works

- Foreman now exposes `board`, `history`, `cost`, and `watch` monitoring
  commands directly from persisted SQLite state
- the board view groups active sprint tasks by status and shows branch, role,
  blocked-reason, step-visit, and token context
- history and cost views surface durable runs, events, and aggregated token or
  USD totals without manual SQL
- watch can render bounded project or run snapshots repeatedly without
  mutating task state

## What is incomplete

- `foreman watch` is still a polling snapshot, not a true live event stream
- dashboard and task-detail UI work are still pending
- the CLI still requires explicit `--db PATH` selection because engine-level
  database discovery does not exist yet

## Known regressions

- none identified by the current automated suite

## Schema or migration notes

- no schema changes were required; the monitoring CLI slice reuses existing
  `tasks`, `runs`, and `events` tables plus new read-model helpers in
  `foreman.store`

## Safe branch points

- `feat/monitoring-cli` after monitoring handlers, tests, and repo-memory
  rollover
