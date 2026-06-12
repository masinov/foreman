# Checkpoint: 2026-06-12-review-integration

## What works

- `fix/backend-correctness-hardening` was fast-forward merged to `main` and
  pushed to `origin/main` at `b396fda`.
- The backend review at `docs/specs/review.md` has been read and split into
  sprint-sized phases in `docs/sprints/current.md` and
  `docs/sprints/backlog.md`.
- Current `main` already covers review Phase 0.1 and Phase 0.4:
  `engine.role_policy` is emitted after run creation, and merge conflicts use
  the explicit `conflict` outcome.

## What is incomplete

- The remaining review Phase 0 defects are now the next implementation sprint.
- The old queued SQLite sprint for active-run lease and heartbeat recovery is
  still useful but should wait until Phase 0 is complete.
- The local checkout has no `./venv`, so validation commands could not run in
  this environment.

## Known regressions

- `signal.task_created` still references an unbound `run` in
  `foreman/orchestrator.py`.
- `foreman waive-merge` still calls `uuid4()` without importing it.
- Dashboard human messages can still persist `run_id="none"` for run-less
  tasks.
- Dashboard process tracking remains per service instance, so Stop cannot
  reliably terminate a previously spawned process across requests.

## Schema or migration notes

- No schema changes in this checkpoint.
- Review Phase 2 will add migration 11 for meta-agent session persistence.
- Review Phase 3 will add migration 12 for executor overrides and complexity.

## Safe branch points

- `origin/main` at `b396fda`.
- Next implementation branch should be `fix/review-phase0-correctness`.
