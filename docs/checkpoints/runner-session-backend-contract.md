# Checkpoint: runner-session-backend-contract

## What works

- Foreman now has an accepted ADR for runner session scope, approval policy,
  and backend contract boundaries in
  `docs/adr/ADR-0001-runner-session-backend-contract.md`
- repo-memory docs now cite the ADR as the active constraint for future
  runner, monitoring, and dashboard work
- the current Claude and Codex backend differences are documented explicitly
  instead of being left implicit in runner code

## What is incomplete

- persistent session reuse is still only guaranteed during a contiguous
  workflow execution path; fresh orchestrator invocations do not yet reload the
  last same-role session from SQLite
- live dashboard activity transport is still undecided
- dashboard implementation remains the next product slice

## Known regressions

- none introduced by this documentation-only slice

## Schema or migration notes

- no schema changes were required; this slice records active runtime
  constraints rather than changing persisted state

## Safe branch points

- `docs/runner-session-backend-adr` after ADR-0001, sprint archive, checkpoint,
  and repo-memory rollover
