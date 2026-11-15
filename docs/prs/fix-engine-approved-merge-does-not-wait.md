# PR Summary: fix/engine-approved-merge-does-not-wait

## Summary

- Sprint 59, slice 4. An approved merge is carried out while another task's
  step is running.

## Scope

- What happened (2026-11-12): a merge approved at 18:28:11 was recorded as
  deferred, with the task waiting at `merge`. The engine had started
  another task's develop step at 18:27:52 and would only look at the
  waiting task after that task finished or parked.
- Now: `ForemanOrchestrator._carry_out_approved_merges`, called from the
  step's command poll, finds tasks of the project that are `in_progress` at
  a `_builtin:merge` step and runs them with `only_roles` set to the merge
  and mark-done steps. `WorkflowRunner` gained `only_roles`: a task whose
  next step has another role is saved at that step, its lease released.
- The check is made at most every ten seconds
  (`approved_merge_check_seconds`).

## Files changed

- `foreman/orchestrator.py`, `foreman/engine/workflow_runner.py`
- `tests/test_engine_approved_merges.py` (new)
- `docs/adr/ADR-0011-resident-engine-and-project-lock.md`,
  `docs/STATUS.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- This runs one task's merge inside another task's step loop. It is limited
  to two built-in steps and guarded against re-entry, and a failure blocks
  only the merged task; but it is the change in this sprint most likely to
  surprise, and it has been run only against scripted runners.
- While a merge runs (seconds; longer if the project's merge step is slow)
  the running agent's output is not read and commands are not heard.
- The running task keeps working on a base that has just moved. That was
  already possible (an operator commit) and is handled at its next step.

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1361 tests, 5 skipped)
- frontend lint, tests and build (unchanged code)

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- With one task at its merge gate and a second task's develop step running,
  an approval is merged and the first task is done before the second
  task's step ends. Steps other than merge and mark-done are not run for
  the other task. The check is not made on every tick.

## Follow-ups

- none
