# fix/retry-and-quota

## Summary

Sprint 56 slice 10a (review finding E9).

## Scope

- `run_with_retry` chooses what the next attempt runs with: `resume` (the
  failed attempt opened a session: continue it with a short "you were
  interrupted" prompt), `session_dropped` (the session id it was given is
  unknown to the backend, or failed twice before starting: fresh session,
  full prompt), or `replay`. `agent.infra_error` carries `next_attempt`,
  the attempt's `cost_usd` and `session_id`, and `dropped_session_id`.
- Orchestrator: the cost of failed attempts is added to the run's cost; a
  dropped session id is not recorded as the run's session.
- Claude Code runner: a rate-limit notice decides whether an error is a
  quota stop; "allowed" notices are remembered; the text fallback is the
  CLI's own phrases only.

## Files changed

`foreman/runner/base.py`, `foreman/runner/claude_code.py`,
`foreman/orchestrator.py`, `tests/test_runner.py`,
`tests/test_runner_claude.py`, `tests/test_orchestrator.py`, changelog,
sprint.

## Migrations

None.

## Risks

- A resumed session depends on the backend having saved the interrupted
  session. If it did not, that attempt fails without opening a session and
  the next one drops the id.
- The Codex runner emits no `agent.session` event, so its retries still
  replay; only the stale-session drop applies to it.

## Tests

Full Python suite and `ruff check`.

## Acceptance criteria satisfied

Slice 10a as written in `docs/sprints/current.md`.

## Follow-ups

Slices 10b and 10c.
