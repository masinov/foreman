# PR Summary: fix/cancelled-dependency-blocks

## Summary

Sprint 54 live-run fix F4. `_dependencies_satisfied` counted a cancelled
dependency as satisfied, so cancelling one queued task released the task
that depended on it, and the resident engine started a developer on it
before the operator's second cancel was applied; that cancel then lost to
the engine's own `in_progress` write. A cancelled prerequisite is a planning
decision, not a delivery.

## Scope

- `foreman/orchestrator.py`: only `done` satisfies; `select_next_task` blocks
  a `todo` task with a cancelled dependency through `block_task_for_error`
  (reason "Dependency cancelled: <ids>. Re-plan the task, then `foreman task
  unblock` it or cancel it.", attention trigger `dependency_cancelled`),
  once, and moves on to the next candidate.
- `foreman/digest.py`: a label for the new trigger.
- `foreman/cli.py`, `foreman/dashboard_service.py`: cancelling a task that
  has a running run while an engine lease is held is refused with a pointer
  to `foreman engine stop-task`; with no engine resident a stale running run
  does not protect the task.
- Docs: `docs/MANUAL.md`, `CHANGELOG.md`, `docs/STATUS.md`,
  `docs/sprints/current.md`, `docs/reviews/sprint-54-live-run-notes.md`.

## Files changed

- `foreman/orchestrator.py`, `foreman/digest.py`, `foreman/cli.py`,
  `foreman/dashboard_service.py`
- `tests/test_orchestrator.py` (+1), `tests/test_cli.py` (+1),
  `tests/test_dashboard.py` (+1)
- `docs/MANUAL.md`, `CHANGELOG.md`, `docs/STATUS.md`,
  `docs/sprints/current.md`, `docs/reviews/sprint-54-live-run-notes.md`,
  `docs/prs/fix-cancelled-dependency-blocks.md`

## Migrations

- none

## Risks

- Projects that relied on cancelled dependencies releasing their dependents
  will see those tasks blocked with an attention turn on the next pass; the
  reason names the cancelled ids and the way out.
- The cancel guard reads the engine lease; a crashed engine's lease protects
  a running run for at most the lease duration (120 s).

## Tests

- `./venv/bin/python -m unittest discover -s tests` (count in the merge
  commit); `scripts/validate_repo_memory.py` clean.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- a cancelled dependency never releases its dependent,
- the dependent is parked once with attention and a clear reason,
- a task being worked on cannot be cancelled underneath the engine.

## Follow-ups

- The engine's `select_next_task` write still races a cancel issued in the
  same second; the command table (`stop_task`) is the ordered path.
