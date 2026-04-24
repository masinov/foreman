# PR Summary: feat/cli-task-show-visibility

## Summary

Adds a direct task-inspection CLI command so operators can inspect one task's
current state, active or latest run, and recent events without opening SQLite
manually or inferring liveness from the working tree.

## Scope

- Added `foreman task show <task_id>` with optional `--runs` and `--events`
  limits
- Summarizes:
  - task metadata and status
  - step visit counts
  - branch and assigned role
  - active run when one exists
  - latest run when no active run exists
  - latest event
  - recent runs
  - recent events
- Added CLI regression coverage using the existing monitoring fixture

## Files changed

- `foreman/cli.py` — `handle_task_show()` and parser wiring
- `tests/test_cli.py` — coverage for `task show`
- `docs/STATUS.md` — branch note and rationale

## Migrations

- none

## Risks

- This is an inspection surface only; it does not fix stale-run recovery by
  itself
- Output is intentionally summary-level, not a full verbatim transcript of
  native subprocess execution

## Tests

- `./venv/bin/python -m pytest tests/test_cli.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Screenshots or output examples

Example:

```text
Task
Database: /repo/.foreman.db
Task: task-1 | Render activity feed
Status: in_progress | type=feature | created_by=human
Current step: review
Active run: run-123 | role=code_reviewer | step=review | status=running
Latest event: 2026-03-30T09:41:12Z | signal.completion | role=code_reviewer | summary=Add more activity detail.
```

## Acceptance criteria satisfied

- [x] Operators can inspect one task directly from the CLI
- [x] Output includes current task state plus recent runs and events
- [x] Regression coverage proves the command shape against seeded monitoring data

## Follow-ups

- Add a similar project-level inspection surface for active sprint state if task
  visibility still leaves too much context hidden during live runs
