# PR Summary: feat-native-backend-preflight-checks

## Summary

- add explicit native backend preflight handling for Claude Code and Codex
- make startup failures fail once before `agent.started` instead of consuming
  infrastructure retries
- roll repo memory forward from backend preflight checks to event-retention
  pruning

## Scope

- add shared non-retryable preflight failure handling in the runner retry
  helper
- validate required executables for Claude Code and Codex before launch
- classify malformed Codex startup responses as preflight failures
- add unit and orchestrator coverage for no-retry preflight behavior
- archive sprint 17 and define sprint 18

## Files changed

- `foreman/runner/base.py` — added `PreflightError` and non-retryable
  handling in `run_with_retry`
- `foreman/runner/__init__.py` — exported `PreflightError`
- `foreman/runner/claude_code.py` — added executable and startup preflight
- `foreman/runner/codex.py` — added executable and startup-contract preflight
- `tests/test_runner.py` — added no-retry preflight coverage
- `tests/test_runner_claude.py` — added Claude executable preflight coverage
- `tests/test_runner_codex.py` — added Codex executable and startup-contract
  preflight coverage
- `tests/test_orchestrator.py` — added orchestrator coverage proving
  preflight failures do not consume retry budget
- `README.md`, `docs/STATUS.md`, `docs/sprints/current.md`,
  `docs/sprints/backlog.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
  `docs/TESTING.md`, `docs/RELEASES.md`, `CHANGELOG.md` — aligned repo memory
  to the completed slice
- `docs/sprints/archive/sprint-17-native-backend-preflight-checks.md` —
  archived the completed sprint
- `docs/prs/feat-native-backend-preflight-checks.md` — branch summary

## Migrations

- none

## Risks

- preflight currently validates executable presence and Codex startup contract
  assumptions, not downstream auth or service reachability
- `foreman watch` still does not match the dashboard's live transport model
- Codex still persists token usage without USD pricing

## Tests

- `./venv/bin/python -m py_compile foreman/runner/base.py foreman/runner/__init__.py foreman/runner/claude_code.py foreman/runner/codex.py tests/test_runner.py tests/test_runner_claude.py tests/test_runner_codex.py tests/test_orchestrator.py`
- `./venv/bin/python -m unittest tests.test_runner.RunWithRetryTests.test_does_not_retry_preflight_error tests.test_runner_claude.ClaudeCodeRunnerTests.test_run_raises_preflight_error_when_executable_is_missing tests.test_runner_codex.CodexRunnerTests.test_run_raises_preflight_error_when_executable_is_missing tests.test_runner_codex.CodexRunnerTests.test_run_raises_preflight_error_when_thread_start_response_is_malformed tests.test_orchestrator.ForemanOrchestratorTests.test_native_runner_preflight_failure_is_not_retried -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- missing or misconfigured native backends fail before long-running execution
  begins
- automated tests cover Claude Code and Codex preflight failure modes
- docs explain backend assumptions and operator recovery clearly enough for
  fresh agents and operators

## Follow-ups

- implement `sprint-18-event-retention-pruning`
- decide whether backend preflight should expand into auth or service
  reachability checks later
