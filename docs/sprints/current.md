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
| F3 | Live-run fix: task branch refreshed from the default branch at every develop visit; an unconcluded merge is never aborted; approve/deny report a quota pause honestly | done | `fix/task-branch-refresh` | git, orchestrator, CLI, tests |
| F4 | Live-run fix: a cancelled dependency blocks the dependent task for re-planning instead of releasing it; cancel refuses a task with a live run | done | `fix/cancelled-dependency-blocks` | orchestrator, CLI, dashboard, tests |
| F5 | Live-run fix: a killed or interrupted run keeps the backend session announced at start, so a pause or shutdown resumes the conversation | done | `fix/keep-session-on-kill` | orchestrator, tests |
| 3 | Intake endpoint: project-level, API-token authenticated, idempotent on an external reference, source metadata, initial status `todo`; sprint optional over a continuous queue | done | `feat/task-add-the-intake-endpoint-and-api-tokens-v2` (engine-run) | `foreman/api_tokens.py`, migration 17 (`api_tokens` + task source columns), `POST /api/projects/{id}/intake`, `foreman token`, drawer Source section, ADR-0013, MANUAL §25, `tests/test_intake.py` |
| 4 | Policy matrix v1: `triage` and `notification` policies join `merge_approval` and `plan_approval`; task-type rules; per-task overrides | todo | | settings, models, orchestrator, tests |
| 5 | Planner step per task producing criteria and a protected acceptance test; architect role repurposed to once-per-task | todo | | role, workflow, tests |
| 6 | Worktree per task under a Foreman-owned directory | done | `feat/task-give-every-task-its-own-git-worktree` (engine-run) | `foreman/worktrees.py`, migration 16, orchestrator, built-ins, `foreman worktree`, ADR-0012, `tests/test_worktrees.py` |
| 6b | Bounded worktree disk use (`max_live_worktrees`) and a per-worktree environment (`worktree_setup_command`); dashboard prune control | done | `chore/task-c68378a4e541` (engine-run, follow-up from ADR-0012) | `enforce_worktree_limit`, setup command + marker, `GET/POST /api/projects/{id}/worktrees[/prune]`, `WorktreePanel`, ADR-0012 amendment, tests |

### Operator UI fix — Project header

- Status: done (unmerged); branch `fix/dashboard-project-header`, following the
  Manager fix at `1690a2a`.
- User-requested descriptor order: Repository, Branch, Workflow. Worktree
  details remain with the descriptors; engine residency/heartbeat and blocked
  counts form a single plain-text status row below them.
- Deliverables: header markup and consistent spacing, rebuilt frontend and
  live browser validation with Manager folded and open.
- Validation passed: 39 frontend tests, production build, repository memory
  checks and live browser assertions for descriptor order, status placement
  and plain-text styling. Screenshots inspected at 1440 × 1000.

### Operator UI fix — Manager panel

- Status: done; branch `fix/dashboard-manager-panel` (unmerged).
- User-reported correction: Manager starts folded in the sprint overview,
  with a Manager tab distinct from the sprint's Agent execution activity.
- Deliverables: lazy opening, retained draft/chat when folded, explicit
  Manager layout names, frontend regression coverage and rebuilt assets.
- This focused fix does not revive the withdrawn dashboard UX refactor.
- Validation: 39 frontend tests, production build, repo memory validation,
  and live browser checks for folded default, open/fold/reopen, reload and
  separate sprint execution activity all passed.

### Slice 1 notes

Landed by the engine in three gate rounds (one deny with corrections, one
merge conflict against a moved `main`), 49 minutes and $21.96 end to end;
the full account is in `docs/reviews/sprint-54-live-run-notes.md`. Two
decisions worth carrying forward:

- The engine lock is a lease row (`resource_type="engine"`), not a lock file,
  so no migration was needed and a crashed engine frees its project by expiry
  (120 s) rather than leaving state a human must clean up. ADR-0011.
- The dashboard's Run button still spawned a `foreman run` subprocess, which
  competed for that lock instead of cooperating with the resident worker. This
  was the concrete reason slice 2 came next; slice 2b closed it.

### Slice 3 notes

Two numbers in the task description were already taken by slice 6, which
landed first: migration 16 (`tasks.worktree_path`) and ADR-0012
(worktree-per-task). Intake therefore landed as **migration 17** and
**ADR-0013**, verified against a version-16 database. Nothing else about the
slice changed.

Two decisions worth carrying into slice 4 (policy matrix):

- **Idempotency uses the caller's key**, `(project, source.system,
  source.external_ref)`, not one Foreman generates — the caller is what
  retries, and a Foreman-generated key would make callers store Foreman state
  to retry safely. A caller that sends neither field gets a new task per call.
- **The intake queue is a sprint** (`<project>-intake`, created on first use,
  `active` unless another sprint is running). The alternative — a nullable
  `tasks.sprint_id` — would have forced task selection, the board, the digest,
  and the context projection each to grow an orphan path. Sprints stay the
  unit of grouping; a continuous queue is a sprint that never completes.

Intake tasks land as `todo`. The `triage` status is slice 4's, as is anything
that ages or bounds the queue: nothing prunes it today.

### Slice 6 notes

Landed out of the numbered order because the live runs kept breaking on the
shared working tree, not on anything slices 3–5 would fix
(`docs/reviews/sprint-54-live-run-notes.md`, observations 7, 19, 33, 35). The
engine no longer checks a branch out in `project.repo_path` at all: each task
gets `<repo>/.foreman/worktrees/<task-key>/`, merges land through a shared
`_integration` tree pinned to the default branch, and the operator's checkout
only sees refs move. ADR-0012. Two decisions worth carrying forward:

- `worktree_link_paths` had to exist for the slice to be usable at all. A
  worktree is a clean checkout, so this repo's own `test_command`
  (`./venv/bin/python …`) has no interpreter until `venv` is symlinked in.
  Superseded by slice 6b: the `foreman` project now sets
  `worktree_setup_command` to build a per-tree venv and editable install, and
  `worktree_link_paths` is empty. Sharing the operator's venv meant a task's
  test run was never really isolated from it.
- `tests/test_cli.py` reinstalled the package into `./venv` from whatever
  checkout ran it, which inside a worktree would repoint the operator's
  virtualenv at a tree `mark_done` later deletes. It now runs
  `python -m foreman` with `PYTHONPATH` pinned to the checkout under test and
  only reinstalls when the virtualenv already points there.

### Slice 6b notes

The two follow-ups ADR-0012 recorded, closed together because they are the
same question — what a worktree costs and what it contains.

- The follow-up suggested "pruning the oldest paused task's tree under
  pressure". Implementing it that way would have been wrong: *paused* is
  exactly when a tree holds uncommitted work, so the policy would most often
  destroy the state worktrees exist to preserve. `enforce_worktree_limit`
  orders by age but gates on **cleanliness** — a clean tree holds nothing its
  branch does not, a dirty one is never taken, and a project whose candidates
  are all dirty exceeds its cap and says so
  (`engine.worktree_limit_exceeded`). The cap is a ceiling the engine reaches
  for, not an invariant.
- Provisioning a tree's own venv costs about six seconds and runs once per
  tree. The setup marker lives in the tree's **git admin directory**, not the
  tree: an untracked marker file would make the tree dirty and block
  `_builtin:merge`. That constraint applies to whatever the setup command
  itself creates, which is why the manual calls out that its output must be
  gitignored.
- Verified end to end rather than by unit test alone: a worktree provisioned
  from scratch by the new setting runs all 830 tests green on its own
  interpreter, with `git status --porcelain` empty afterwards.

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
