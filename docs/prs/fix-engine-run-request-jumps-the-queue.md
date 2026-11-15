# PR Summary: fix/engine-run-request-jumps-the-queue

## Summary

- Sprint 59, slice 3. A task asked for by name runs next, not after the
  queue.

## Scope

- What happened (2026-11-12): `run_task` for one task was requested at
  17:50 while the engine was working through the sprint. The engine
  accepted it at once and queued it "for the next pass". A pass ends only
  when no task can be picked, so the request waited until 18:28, when the
  engine was shut down and restarted; the new engine ran it first. (The
  command's `acknowledged_at` reads 18:28 because the restart stamped it
  again.)
- Now: `ForemanOrchestrator.yield_between_tasks`, set by a resident engine,
  is asked after each task of a pass. It is true when a run request is
  queued or a command is pending; the pass then ends with `yielded`, the
  loop drains commands, and the next pass runs the requested task.
- `foreman serve --once` and `foreman run` do not set it: a single pass
  would leave the rest of the queue unrun.
- A request is checked again when its turn comes. If the task is no longer
  todo or resumable, the command is completed with that reason and the
  task is not run.

## Files changed

- `foreman/orchestrator.py`, `foreman/serve.py`
- `tests/test_serve.py`
- `docs/STATUS.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- A requested task still waits for the task in hand to finish; a long
  develop step is not interrupted for it.
- The step loop is unchanged; only where a pass ends changed. Covered by
  tests with a real orchestrator whose task run is replaced; not run with a
  real agent.

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1358 tests, 5 skipped)
- frontend lint, tests and build (unchanged code)

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- With three queued tasks and a request for the third made during the
  first, the order run is first, third, second. The test fails without the
  change.

## Follow-ups

- none
