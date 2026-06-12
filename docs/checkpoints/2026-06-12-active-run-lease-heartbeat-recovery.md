# Checkpoint: 2026-06-12-active-run-lease-heartbeat-recovery

## What works

- Native Claude/Codex runner streams can renew the task lease while a step is
  still running.
- Active-run recovery can distinguish recent live lease holders from stale
  holders by heartbeat age.
- Recovery force-expires the recovered task lease before resetting the task to
  `todo`.
- Regression coverage exercises forced lease expiry, crash event token
  redaction, live-holder protection, and native stream heartbeat behavior.

## What is incomplete

- The heartbeat is event-driven. A backend that produces no stream events for a
  long time has no independent timer-based renewal in this slice.

## Known regressions

- none known

## Schema or migration notes

- No schema migration. `ForemanStore.expire_resource_leases()` now accepts
  `force=True` to expire active leases for recovery.

## Safe branch points

- Branch: `feat/active-run-lease-heartbeat-recovery`
- Base: `main` at `7790a8f`
