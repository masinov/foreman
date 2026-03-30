# Checkpoint: codex-runner

## What works

- Foreman now has a native Codex runner that drives `codex app-server` over
  stdio JSON-RPC, starts or resumes threads, and normalizes streamed agent
  items into Foreman events
- the orchestrator can execute Codex-backed roles without an injected scripted
  executor
- persistent Codex thread ids are stored on task runs and reused for later
  developer turns on the same task
- human-gate approvals now resume immediately for native backends when the
  target repo is available, while still deferring safely when it is not

## What is incomplete

- monitoring CLI surfaces are still missing
- Codex app-server does not expose USD pricing, so Codex run costs still
  persist as `0.0`
- there is no explicit CLI preflight for `claude` or `codex` yet

## Known regressions

- none identified by the current automated suite

## Schema or migration notes

- no schema changes were required; the Codex runner slice reuses existing
  `runs` and `events` tables

## Safe branch points

- `feat/codex-runner` after native Codex integration, human-gate resume fix,
  tests, and repo-memory rollover
