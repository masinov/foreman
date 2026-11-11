# PR Summary: fix/crash-safe-steps

## Summary

- Sprint 56 slice 2. A crash or an engine error costs one step and leaves
  no run stuck in `running`.

## Scope

- The transition write sets `workflow_current_step` to the next step.
- `run_workflow_from_step` settles open runs as failed when an unexpected
  exception escapes a step, then re-raises.
- Built-in steps record `duration_ms`.
- Stacked on `fix/default-branch-check`.

## Files changed

- `foreman/orchestrator.py`, `tests/test_orchestrator.py`
- `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- A task that used to sit `in_progress` with no step between steps now
  always has one; anything that read "no step" as "mid-transition" sees
  that state only at the start of a task.

## Tests

- `python -m unittest discover -s tests`: 1043 pass, 1 skipped (2 new)
- `ruff check foreman tests scripts`: clean

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- An engine killed after develop hands over to test leaves the task at
  `test`; the next engine runs test and review without re-running develop.
- A built-in that raises leaves its run `failed` with the error text.

## Follow-ups

- Resume a stale agent step in place (slice 10).
