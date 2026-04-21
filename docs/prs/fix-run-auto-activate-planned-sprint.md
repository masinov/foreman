# PR Summary: fix/run-auto-activate-planned-sprint

## Summary

- move first-planned-sprint activation into the backend project run path
- make `foreman run <project>` consume queued work even when no sprint is
  currently active
- add orchestrator and CLI regression coverage for the no-active-sprint case
- enforce `cost_limit_per_sprint_usd` in the orchestrator so unattended sprint
  execution blocks when the persisted sprint budget is exhausted
- preserve actionable native runner failure details on blocked tasks instead of
  replacing them with the generic workflow fallback
- honor project-level `time_limit_per_run_minutes` in executor run config while
  keeping the legacy seconds-based override as a fallback
- restore the caller's original git branch after clean successful or blocked
  task runs so backend execution does not leave the repo checkout on task
  branches by default
- prevent directed and autonomous selection from starting new work while a live
  `in_progress` task still owns the sprint
- recover only stale persisted `running` runs during crash recovery, leaving
  fresh active owners untouched

## Scope

- `foreman/orchestrator.py`
- `foreman/executor.py`
- `foreman/git.py`
- `tests/test_orchestrator.py`
- `tests/test_executor.py`
- `tests/test_cli.py`
- `docs/STATUS.md`
- `docs/sprints/current.md`

## Files changed

- `foreman/orchestrator.py`
- `foreman/executor.py`
- `foreman/git.py`
- `tests/test_orchestrator.py`
- `tests/test_executor.py`
- `tests/test_cli.py`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/prs/fix-run-auto-activate-planned-sprint.md`

## Migrations

- none

## Risks

- dashboard start still pre-activates the first planned sprint before spawning
  the subprocess; this branch adds the same behavior to the backend run path so
  CLI and future entrypoints stop depending on the dashboard shim
- empty planned sprints will activate and then idle; this branch does not add
  separate empty-sprint handling
- sprint budget enforcement currently depends on persisted USD totals, so
  backends that only report tokens still need pricing support for full budget
  coverage
- live native runs can still sit in `in_progress` until the runner exits or a
  later orchestrator pass recovers them; this branch now prevents new sprint
  work from starting while that live owner exists, but it does not yet add an
  explicit lease or heartbeat model
- checkout restoration only happens when the worktree is clean, so interrupted
  or still-running task branches can still leave the repo on the task branch
  until a later recovery step handles them

## Tests

- `./venv/bin/python -m pytest tests/test_orchestrator.py -q`
- `./venv/bin/python -m pytest tests/test_executor.py -q`
- `./venv/bin/python -m pytest tests/test_cli.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Screenshots or output examples

- `./venv/bin/foreman run foreman` should no longer treat queued planned
  sprints as an immediate idle condition once the backend slice is complete

## Acceptance criteria satisfied

- backend project runs can pick up the first planned sprint without a
  dashboard-only shim
- orchestrator regression coverage locks the no-active-sprint queue activation
  path down
- CLI regression coverage verifies the shipped `foreman run` surface follows
  the backend behavior
- sprint-wide persisted budget limits can block the next task before Foreman
  burns more cost in an unattended run
- blocked tasks retain concrete native runner failure reasons after retry
  exhaustion or preflight failure
- project-level run timeout settings now reach the native runner config through
  the backend executor path
- directed backend runs restore the caller's original branch after clean task
  completion or clean blocked failure paths
- project runs now wait on fresh active owners instead of starting a second
  task into the same sprint checkout
- crash recovery only fails `running` runs that have actually exceeded the
  configured timeout window

## Follow-ups

- remove redundant dashboard-side sprint pre-activation once the backend-owned
  semantics are fully exercised end to end
- decide whether empty planned sprints should auto-complete, remain active, or
  be rejected at creation time
- add a stronger active-run lease or heartbeat model so recovery does not rely
  only on timeout windows
