# Current Sprint

- No active sprint.
- Last completed sprint: `sprint-46-completion-truth-hardening`
- Last completion time: `2026-04-24T17:07:34Z`
- Branch used to close the stale runtime state: `fix/close-sprint-46-cleanly`
- Next queued sprint in SQLite: `sprint-47-active-run-lease-and-heartbeat-recovery` (planned)

## Most Recent Sprint Outcome

Sprint 46 is complete. Its backend deliverables are all present on local
`main`, including:

- structured completion evidence in the orchestrator and task store
- false-positive completion regression coverage
- merge-time weak-completion guarding
- completion-truth ADR and docs
- reviewer prompt hardening with engine-produced evidence

The main issue at sprint close was not unfinished feature code. It was
operational drift: a hidden host-side `foreman run foreman` process continued
running after the sprint was effectively done, leaving stale `running` rows and
continued repo or SQLite activity that was difficult to inspect from the normal
sandboxed shell.

## Closeout Notes

- All sprint-46 tasks are `done` in SQLite.
- Sprint `sprint-46-completion-truth-hardening` is `completed` in SQLite.
- There are no remaining `running` rows in `runs`.
- The stale hidden host-side Foreman and Claude processes were identified and
  stopped before sprint closeout.

## Why No New Active Sprint Yet

Before starting more autonomous work, Foreman needs the backend hardening that
was exposed by the first supervised runs to be reconciled on `main`.
Transcript logging has landed, and the current manual branch is closing the
remaining correctness gaps around event schema persistence, outcome strictness,
lease fencing, active lease uniqueness, and recovery-token redaction.

## Next Planned Sprint In Queue

- Sprint: `sprint-47-active-run-lease-and-heartbeat-recovery`
- Status: planned in SQLite
- Queue position: next planned sprint, ahead of the older deferred `sprint-008`
- Note: do not start it until `fix/backend-correctness-hardening` lands
