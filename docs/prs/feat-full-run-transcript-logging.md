# PR Summary: feat/full-run-transcript-logging

## Summary

Add durable transcript logging for Foreman runs using the existing SQLite
`events` table, then expose that data through a new `foreman transcript`
command. The goal is to make agent and builtin activity auditable during a run
and afterwards without reconstructing behavior from sparse summary events.

## Scope

- persist the full agent prompt as an event
- persist raw Claude stream-json lines and raw Codex JSON-RPC messages as events
- persist builtin test stdout and stderr incrementally as events, plus the full
  final stdout or stderr payload in the test summary event
- add a CLI transcript reader for one run

## Files changed

- `foreman/builtins.py`
- `foreman/orchestrator.py`
- `foreman/runner/claude_code.py`
- `foreman/runner/codex.py`
- `foreman/cli.py`
- `tests/test_runner_claude.py`
- `tests/test_runner_codex.py`
- `tests/test_orchestrator.py`
- `tests/test_cli.py`
- `docs/STATUS.md`
- `docs/prs/feat-full-run-transcript-logging.md`

## Migrations

- none

## Risks

- event volume will increase because raw runner and builtin output is now
  persisted instead of only normalized summaries
- this first cut optimizes for auditability, not retention or compression

## Tests

- runner unit tests for raw-output event persistence
- builtin transcript logging tests
- CLI transcript command test
- repo-memory validation

## Acceptance criteria satisfied

- a run can be inspected from SQLite with full prompt and raw agent output
- builtin test stdout or stderr is no longer reduced to `output_tail` only
- there is a CLI surface to review a run transcript without truncation

## Follow-ups

- transcript filtering or paging for very large runs
- retention policy for high-volume raw transcript events
- dashboard transcript viewer backed by the same persisted events
