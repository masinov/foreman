# PR Summary: fix/keep-session-on-kill

## Summary

Sprint 54 live-run fix F5. A live `foreman engine pause` stopped a developer
step correctly, but the resumed step started a new Claude session and re-read
the repository: only `agent.completed` and `agent.error` payloads set the
run's `session_id`, and a killed run never reaches either. The backend
announces its session at start (`agent.session`); the engine now keeps it.

## Scope

- `foreman/orchestrator.py`: `_execute_native_runner_step` records the session
  id from `agent.session` as soon as it is seen; `_abandon_run` persists the
  session id found in the run's events (new `_session_id_from_events`) when
  it settles a run as `killed`, so `get_latest_session_id` returns it for the
  next visit.

## Files changed

- `foreman/orchestrator.py`, `tests/test_quota_pause.py` (+1)
- `CHANGELOG.md`, `docs/STATUS.md`, `docs/sprints/current.md`,
  `docs/reviews/sprint-54-live-run-notes.md`, `docs/prs/fix-keep-session-on-kill.md`

## Migrations

- none

## Risks

- Resuming a session that the backend has since discarded falls back to the
  runner's existing behavior (a fresh session); nothing new fails.

## Tests

- `tests.test_quota_pause`, `tests.test_serve`, `tests.test_orchestrator`,
  `tests.test_runner_lifecycle` in the clone; the full suite and
  `scripts/validate_repo_memory.py` on `main` after the merge.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- a killed run keeps its session id,
- the next visit resumes it.

## Follow-ups

- none
