# Checkpoint: claude-code-runner

## What works

- Foreman now has a native Claude Code runner with stream-json parsing,
  structured event mapping, retry normalization, and session resume
- the orchestrator can execute shipped Claude-backed roles without an injected
  scripted executor
- developer session IDs are persisted and reused across repeat developer steps
- runner failures are normalized into durable `agent.infra_error` and
  `agent.error` events on the task run

## What is incomplete

- the Codex backend is still stubbed
- there is no explicit CLI preflight for the `claude` executable yet

## Known regressions

- none identified by the current automated suite

## Schema or migration notes

- no schema changes were required; the runner slice reuses existing `runs` and
  `events` tables

## Safe branch points

- `feat/claude-runner` after native runner integration, tests, and repo-memory
  rollover
