# PR Summary: docs/queue-sprint-47-active-run-recovery

## Summary

Queue the next backend sprint after sprint 46 and record it in repo memory
before starting the next Foreman run. This branch adds sprint 47 as the next
planned sprint and places it ahead of the older deferred planned sprint 8 so
the queue reflects the current backend priority.

## Scope

- `docs/STATUS.md` — current and next queued sprint state
- `docs/sprints/current.md` — sprint 46 remains active, sprint 47 recorded as
  the next queued sprint
- SQLite sprint and task state — add sprint 47 and its five tasks as planned work

## Files changed

- `docs/STATUS.md`
- `docs/sprints/current.md`

## Migrations

- none

## Risks

- sprint 46 is still active, so starting `foreman run foreman` will continue
  sprint 46 first; sprint 47 is queued next rather than activated immediately
- an older planned sprint (`sprint-008`) remains in the database, so sprint 47
  must be queued ahead of it explicitly to become the next planned sprint

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/foreman sprint list foreman`
- `./venv/bin/foreman task list foreman --sprint sprint-46-completion-truth-hardening`

## Acceptance criteria satisfied

- [x] sprint 47 is defined in repo memory
- [x] sprint 47 is queued next in SQLite
- [x] sprint 47 tasks are recorded in SQLite
- [x] active sprint 46 remains truthful in repo memory

## Follow-ups

- start the next Foreman run against the active project
- let sprint 46 finish before the queue advances to sprint 47
