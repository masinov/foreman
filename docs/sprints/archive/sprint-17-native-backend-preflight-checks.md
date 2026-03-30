# Sprint Archive: sprint-17-native-backend-preflight-checks

- Sprint: `sprint-17-native-backend-preflight-checks`
- Status: completed
- Goal: fail fast when required Claude Code or Codex native backend
  prerequisites are unavailable or misconfigured
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `docs/adr/ADR-0001-runner-session-backend-contract.md`
  - `foreman/runner/base.py`
  - `foreman/runner/claude_code.py`
  - `foreman/runner/codex.py`
  - `tests/test_runner.py`
  - `tests/test_runner_claude.py`
  - `tests/test_runner_codex.py`
  - `tests/test_orchestrator.py`

## Final task statuses

1. `[done]` Validate native backend availability before execution
   Deliverable: Claude Code and Codex now fail with explicit preflight errors
   when required executables or startup contracts are missing.

2. `[done]` Persist and surface preflight failures cleanly
   Deliverable: backend preflight failures are now non-retryable, persist one
   explicit error, and stay distinct from retryable post-start infrastructure
   failures.

3. `[done]` Document backend startup assumptions and operator recovery
   Deliverable: repo docs now explain required binaries, Codex startup
   expectations, and how operators should recover from preflight failures.

## Deliverables

- shared non-retryable `PreflightError` handling in the runner retry helper
- Claude Code executable preflight before process launch
- Codex executable and startup-contract preflight before `agent.started`
- orchestrator coverage proving preflight failures do not consume retry budget
- repo-memory rollover from backend preflight to event-retention pruning

## Demo notes

- `./venv/bin/python -m unittest tests.test_runner.RunWithRetryTests.test_does_not_retry_preflight_error tests.test_runner_claude.ClaudeCodeRunnerTests.test_run_raises_preflight_error_when_executable_is_missing tests.test_runner_codex.CodexRunnerTests.test_run_raises_preflight_error_when_executable_is_missing tests.test_runner_codex.CodexRunnerTests.test_run_raises_preflight_error_when_thread_start_response_is_malformed tests.test_orchestrator.ForemanOrchestratorTests.test_native_runner_preflight_failure_is_not_retried -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-18-event-retention-pruning`: implement spec-aligned pruning for old
  event rows while preserving active-work history
- `sprint-19-watch-live-tail-alignment`: align `foreman watch` with the
  dashboard live transport and live-tail intent
