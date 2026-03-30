# Checkpoint: orchestrator-main-loop

## What works

- Foreman can select the next directed task from SQLite and execute the shipped
  development workflow end to end through persisted runs and events
- built-ins for tests, merge, mark-done, and human-gate pause now have explicit
  runtime seams
- orchestrator integration tests exercise real git state, carried reviewer or
  test feedback, and workflow fallback blocking

## What is incomplete

- `foreman init` still does not scaffold new repositories or persist initialized
  projects
- context projection into `.foreman/` is still pending
- native Claude Code and Codex runner backends do not exist yet
- human-gate approve and deny resume commands are still pending

## Known regressions

- none known from the orchestrator slice itself

## Schema or migration notes

- no schema migration was required
- the orchestrator currently uses synthetic orchestrator runs for control-path
  events because `events.run_id` is non-null in the current schema

## Safe branch points

- `feat/orchestrator-main-loop` after the orchestrator tests and full unittest
  suite pass
- repo memory rolled forward to `sprint-03-scaffold`
