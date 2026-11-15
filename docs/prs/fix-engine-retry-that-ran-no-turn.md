# PR Summary: fix/engine-retry-that-ran-no-turn

## Summary

- Sprint 59, slice 1. A run that read no prompt is tried again, and the
  correction after a missing completion marker no longer invites a false
  "done".

## Scope

- What happened (FOR-17, 2026-11-12): the developer's first run ended
  without the completion marker. The corrective retry resumed the session;
  the CLI printed two notices about orphaned background tasks and a result
  with `num_turns: 0`, no text, in 36 ms. The engine read that as a second
  answer without a marker and blocked the task.
- Now: a result with no turn, no text and no error raises `NoTurnError`, an
  infrastructure error. `run_with_retry` sends the same prompt to the same
  session again (not "continue where you stopped": nothing was started),
  with the usual back-off and limit.
- Also: two other recorded corrective retries answered "the task is blocked
  ... the marker below only satisfies the output-format request" and ended
  with the marker, which the engine took as done. The correction now says:
  if the work is not finished, do not write the marker, say what is
  unfinished or what blocks it. Without the marker the step ends in error
  and the task is blocked with that text.

## Files changed

- `foreman/runner/base.py`, `foreman/runner/claude_code.py`,
  `foreman/runner/__init__.py`, `foreman/engine/output_contract.py`
- `tests/test_runner_claude.py`, `tests/test_engine_agent_step.py`
- `docs/STATUS.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- Why the CLI returned without a turn is not known (the orphaned background
  tasks are the visible difference). Sending the prompt again is a guess at
  the remedy; if it also returns nothing, the step fails after the retry
  limit as an infrastructure failure, which is at least named correctly.
- The reworded correction relies on the agent following it. Not run against
  a real agent.

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1355 tests, 5 skipped)
- frontend lint, tests and build (unchanged code)

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The recorded result line raises `NoTurnError`; the retry carries the same
  prompt and session; an engine test runs the FOR-17 sequence to done.

## Follow-ups

- none
