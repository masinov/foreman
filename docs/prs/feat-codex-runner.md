# PR Summary: feat/codex-runner

## Summary

- implement the native Codex runner through `codex app-server` JSON-RPC
- integrate Codex into the orchestrator's native backend map and persisted
  session reuse path
- fix immediate human-gate resume for native backends so branch checkout and
  runtime-availability checks are handled correctly
- roll repo memory forward from the Codex runner sprint to the monitoring CLI
  sprint

## Scope

- Codex runner command startup, RPC messaging, event normalization, and
  approval-response handling
- orchestrator native backend defaults and human-gate resume readiness checks
- Codex runner unit coverage and Codex orchestrator integration coverage
- sprint archive, checkpoint, changelog, and roadmap updates

## Files changed

- `foreman/runner/codex.py`
- `foreman/runner/__init__.py`
- `foreman/orchestrator.py`
- `tests/test_runner_codex.py`
- `tests/test_orchestrator.py`
- `README.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-07-codex-runner.md`
- `docs/checkpoints/codex-runner.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `CHANGELOG.md`

## Migrations

- none

## Risks

- the Codex runner depends on a working `codex` executable and app-server
  support in PATH
- Codex app-server currently provides token usage but not USD pricing, so
  `cost_usd` remains `0.0` for Codex-backed runs until a later pricing policy
  lands

## Tests

- `./venv/bin/python -m unittest tests.test_runner_codex tests.test_runner_claude tests.test_orchestrator -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python -m py_compile foreman/runner/codex.py foreman/runner/__init__.py foreman/orchestrator.py tests/test_runner_codex.py tests/test_orchestrator.py`

## Screenshots or output examples

- `foreman approve --db <path>` and `foreman deny --db <path>` now keep
  deferred output only when the next backend or repo runtime is unavailable

## Acceptance criteria satisfied

- the orchestrator can execute a Codex-backed role through a native runner
  implementation
- persistent Codex sessions are reused across eligible workflow steps
- runner failures are normalized into durable run and event history
- docs and validation have been rolled forward to the monitoring CLI sprint

## Follow-ups

- implement `sprint-08-monitoring-cli`
- capture the first runner session and backend ADR now that both native
  backends are present
