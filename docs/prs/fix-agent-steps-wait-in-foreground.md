# fix/agent-steps-wait-in-foreground

## Summary

Found by running sprint 58 through Foreman. The first task (FOR-17) did its
work in 16 minutes and was then blocked with "Missing completion marker".

## What happened

The developer agent ran the Python suite (about 140 s). Claude Code's default
command timeout is 120 s; past it the command is moved to the background and
the agent may end its turn and be "notified" later. In a headless step the
process exits when the turn ends, so the notification never comes. The
corrective retry resumed the session, received only the "orphaned background
task" notices, ran no turn, and the task was blocked.

## Scope

- `foreman/runner/claude_code.py`: `HEADLESS_STEP_ENV` (background commands
  off, 20 minute default and 30 minute maximum command timeout) merged under
  the role's own environment for every step.
- `foreman/data/roles/developer.toml`, `developer_worker.toml`: the prompt
  says a step ends when the message ends.
- Tests: the environment is always set; a role can override it.

## Files changed

`foreman/runner/claude_code.py`, two role files, `tests/test_runner_claude.py`,
changelog.

## Migrations

None.

## Risks

A command that really needs more than 30 minutes fails instead of being
backgrounded. The test step is the engine's own and is not affected.

## Tests

`tests/test_runner_claude.py`, whole suite.

## Follow-ups

- A corrective retry that runs no turn is recorded as a second contract
  failure and blocks the task. It should be told apart from an agent that
  answered without the marker.
- Both runs of the task carry the same cumulative session cost ($4.99), so
  the task total counts it twice.
- The Codex runner has no equivalent guard.
