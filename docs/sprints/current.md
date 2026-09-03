# Current Sprint

- Active implementation sprint: **none.** Sprint 53 (Phase 0 unattended
  safety) closed on 2026-09-04 and is archived at
  `docs/sprints/archive/sprint-53-phase0-unattended-safety.md`.
- Next: open sprint 54 from Phase 1 of the production readiness roadmap in
  `docs/sprints/backlog.md`. Suggested first slices, in dependency order:
  1. `foreman serve` resident worker with a project engine lock, SIGTERM
     handling, structured logging, a command table, and a dead-letter state.
  2. Intake endpoint (project-level, API-token authenticated, idempotent on an
     external reference, policy-chosen initial status) with sprints optional
     over a continuous queue.
  3. Policy matrix v1 (intake triage and notification join the existing merge
     and plan gate policies).
  4. Planner step per task producing criteria and a protected acceptance test.
  5. Worktree per task; pull-request integration; facts-based verification.

## Previous sprint

Sprint 53 — Phase 0 unattended safety. Six slices, all merged to `main`:
store safety (`9d23fe0`), runner process lifecycle (`79d499a`), output
contract and signals (`2d9829a`), workflow order and merge gate (`10333ef`),
dashboard minimum safety (`8074eda`), cleanup (sprint close). Full suite at
close: 605 backend tests, 18 frontend tests. Checkpoint:
`docs/checkpoints/2026-09-04-sprint-53-phase0-unattended-safety.md`.
