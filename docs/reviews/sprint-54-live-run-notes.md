# Sprint 54 live-run notes

Foreman driving Foreman. Each slice of sprint 54 that the engine can carry
is planned as a dogfood task in the repository's own `.foreman.db` and run
with `foreman run foreman`. This file records what the engine did, what a
person had to do, and every deficiency observed, with a severity:

- **blocker** — the pipeline cannot complete the task without a person or a
  code change; fixed inside the sprint.
- **major** — the task completes but the outcome or the audit trail is
  wrong or misleading; queued as a sprint slice or backlog item.
- **minor** — friction; recorded for the backlog.

## Setup (2026-09-04)

- Dogfood project `foreman`, workflow `development`, `task_selection_mode=directed`.
- Settings changed for the live run: `merge_approval=human` (a person
  inspects the branch before the engine merges), `default_model=claude-opus-5`
  for the developer role, `cost_limit_per_task_usd=75` as a ceiling.
- The previous dogfood sprint (`Review Phase 0 correctness`) was stale: its
  one task had been done by hand months ago. Cancelled and completed by hand.
- Slice 1 (`foreman serve`) was planned by hand as a full task description
  plus acceptance criteria (see the task record); the engine has no planner
  step yet (sprint 54 slice 5).

## Observations

_(filled in as runs happen)_
