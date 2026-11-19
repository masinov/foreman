# PR Summary: fix/stale-run-resumes-in-place

## Summary

- A stale `running` run of a task that has a step is recovered at that
  step: the task keeps its step, carried output and visit counts, and a
  developer resumes the session the stale run recorded. A task with no step
  starts again from the entry step, as spec 6.6 says.

## Scope

- `foreman/engine/recovery.py` (`recover_stale_running_runs`).

## Files changed

- `foreman/engine/recovery.py`, `tests/test_engine_recovery.py`,
  ARCHITECTURE, CHANGELOG, backlog, sprint file.

## Migrations

- none

## Risks

- A step that keeps dying is still bounded by its visit limit, which now
  counts the dead attempts.

## Tests

- `test_a_stale_run_resumes_its_step_in_place_rather_than_the_task`: an
  engine dead during review; the review runs again with its carried output
  and the developer does not. Fails before the change.
- `test_a_stale_developer_run_resumes_its_session`: the developer is handed
  the dead run's session. Fails before the change.
- Full suite, ruff, `lint-imports`.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A stale `running` agent run is resumed in place.

## Follow-ups

- none
