# Current Sprint

## Sprint 54 — Phase 1: resident engine and intake

- **Opened:** 2026-09-04, from Phase 1 of
  `docs/reviews/production-readiness-review.md`
- **Status:** in_progress
- **Method:** slices are planned by hand and executed through Foreman
  itself (`foreman run foreman`) where the engine can carry them, so the
  sprint doubles as a live evaluation of the product. Findings from those
  runs are recorded in `docs/reviews/sprint-54-live-run-notes.md` and turn
  into fixes inside the sprint when they block the pipeline.

### Goal

Turn the one-shot engine into a resident service that other systems can
hand work to, with autonomy decided by policy: a `foreman serve` worker
that never needs a person to press Run, a command table the dashboard and
CLI write to, a project-level intake endpoint, and a policy matrix that
decides where a human is required.

### Slices

| # | Slice | Status | Branch / task | Deliverable |
|---|-------|--------|---------------|-------------|
| 1 | `foreman serve` resident worker: project engine lock with a timer heartbeat, idle wake on `data_version`, SIGTERM stop, per-task failure isolation with backoff, structured JSON logs | done (engine-run, merged `a462659`) | `feat/task-add-foreman-serve-resident-engine-worker-with-a-project-engine-lock` / dogfood task `task-add-foreman-serve-…` | `foreman/serve.py`, `foreman/engine_lock.py`, `foreman/logs.py`, `foreman serve`, ADR-0011, `tests/test_serve.py` |
| 2a | Engine command table and `foreman engine` CLI: `pause`, `resume`, `run_task`, `stop_task`, `shutdown` consumed by the resident engine; migration 15 | done (merged `fd28d94`) | dogfood task `task-add-the-engine-command-table-and-foreman-engine-cli` (engine-run, depends on 1) | migration, `engine_commands`, `foreman engine`, tests |
| 2b | Dashboard onto the resident engine: status from the engine lock, Run/Stop through commands, no process handles; `blocked_kind` (gate vs engine) reporting | done | `feat/task-rewire-the-dashboard-onto-the-resident-engine-and-report-dead-letter-tasks` (engine-run, depends on 2a) | `foreman/engine_control.py`, service, API, frontend, ADR-0002 amendment, tests |
| F1 | Live-run fix: backend progress lines no longer persisted as tool uses; tool results capped | done (`2dacef3`) | `fix/runner-progress-lines` | runner, tests |
| F2 | Live-run fix: backend quota exhaustion pauses the task until the reset instead of blocking it; `foreman serve` waits; idle passes logged once | done | `fix/runner-quota-exhaustion` | runner, orchestrator, serve, CLI, tests |
| 3 | Intake endpoint: project-level, API-token authenticated, idempotent on an external reference, source metadata, policy-chosen initial status; sprint optional over a continuous queue | todo | | `POST /api/projects/{id}/intake`, tokens, tests |
| 4 | Policy matrix v1: `triage` and `notification` policies join `merge_approval` and `plan_approval`; task-type rules; per-task overrides | todo | | settings, models, orchestrator, tests |
| 5 | Planner step per task producing criteria and a protected acceptance test; architect role repurposed to once-per-task | todo | | role, workflow, tests |
| 6 | Worktree per task under a Foreman-owned directory | todo | | `foreman/git.py`, orchestrator, tests |

### Slice 1 notes

Landed by the engine in three gate rounds (one deny with corrections, one
merge conflict against a moved `main`), 49 minutes and $21.96 end to end;
the full account is in `docs/reviews/sprint-54-live-run-notes.md`. Two
decisions worth carrying forward:

- The engine lock is a lease row (`resource_type="engine"`), not a lock file,
  so no migration was needed and a crashed engine frees its project by expiry
  (120 s) rather than leaving state a human must clean up. ADR-0011.
- The dashboard's Run button still spawns a `foreman run` subprocess, which now
  competes for that lock instead of cooperating with the resident worker. This
  is the concrete reason slice 2 (the engine command table) comes next.

### Slice 2b notes

The dashboard's process registry is gone: Run enqueues `resume` (plus
`run_task` for a task-scoped start), Pause enqueues `pause`, and a task Stop
enqueues `stop_task`. The concern raised in the slice 1 notes — the Run button
competing for the engine lock instead of cooperating with the resident worker
— is closed: the only process the dashboard starts is a detached
`foreman serve` when nothing holds the lock, and it keeps no handle on it.

Two things worth carrying forward:

- The paused flag lives in the serve process's memory, so no other process can
  read it. `engine_control.engine_is_paused()` derives it from the last
  *applied* `pause`/`resume`/`shutdown` in the command log instead. That is
  correct for every state the engine reaches through a command, and wrong only
  for an engine paused by something that left no command row — which nothing
  currently does.
- `blocked_kind` is derived from the workflow definition, not stored, so no
  migration and no new status. The tie-break when a workflow will not load is
  the human-gate builtin's own `blocked_reason`.

### Decisions taken at open

- Git host for pull-request integration: **GitHub** (the origin remote is
  `github.com`); the integration slice is queued for sprint 55 on top of
  worktrees and uses `gh`.
- Identity provider and notification channel: **not decided**; the login
  and notification slices stay in the backlog until they are.

### Live-run protocol

1. Plan the slice as a dogfood task with a full description and
   acceptance criteria (`foreman task add`).
2. `merge_approval=human` on the dogfood project: the engine develops,
   tests, reviews, and pauses; a person inspects the branch and runs
   `foreman approve`, which merges.
3. Every deficiency observed (prompting, context, gates, evidence, git,
   dashboard) goes into the live-run notes with a severity and, when it
   blocks the pipeline, a fix slice in this sprint.

## Previous sprint

Sprint 53 — Phase 0 unattended safety. Six slices, all merged to `main`:
store safety (`9d23fe0`), runner process lifecycle (`79d499a`), output
contract and signals (`2d9829a`), workflow order and merge gate (`10333ef`),
dashboard minimum safety (`8074eda`), cleanup (`3e6bb18`). Full suite at
close: 605 backend tests, 18 frontend tests. Checkpoint:
`docs/checkpoints/2026-09-04-sprint-53-phase0-unattended-safety.md`.
