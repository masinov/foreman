# PR Summary: feat/claude-runner

## Summary

- implement the first native Claude Code runner backend
- integrate native runner execution and retry handling into the orchestrator
- carry forward the previously approved sprint-05 archive, checkpoint, and PR
  summary artifacts that were present but untracked in the starting repo state
- roll repo memory forward from the Claude runner sprint to the Codex runner
  sprint

## Scope

- shared runner protocol and retry helpers
- Claude stream-json parsing and signal extraction
- orchestrator-native execution path for shipped Claude-backed roles
- runner and orchestrator test coverage
- tracked carry-forward of the missing sprint-05 repo-memory artifacts from the
  local baseline
- sprint archive, checkpoint, changelog, and roadmap updates

## Files changed

- `foreman/runner/base.py`
- `foreman/runner/signals.py`
- `foreman/runner/claude_code.py`
- `foreman/runner/__init__.py`
- `foreman/orchestrator.py`
- `tests/test_runner_claude.py`
- `tests/test_orchestrator.py`
- `README.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-06-claude-runner.md`
- `docs/checkpoints/claude-code-runner.md`
- `docs/sprints/archive/sprint-05-human-gates.md`
- `docs/checkpoints/human-gate-resume.md`
- `docs/prs/feat-human-gate-resume.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `CHANGELOG.md`

## Migrations

- none

## Risks

- the native Claude runner depends on a working `claude` executable in PATH
- project `default_model` is still passed through without backend validation,
  so mismatched model/backend combinations remain a runtime configuration risk

## Tests

- `./venv/bin/python -m unittest tests.test_runner_claude tests.test_orchestrator -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python -m py_compile tests/test_runner_claude.py tests/test_orchestrator.py foreman/runner/base.py foreman/runner/signals.py foreman/runner/claude_code.py foreman/orchestrator.py`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- the orchestrator can execute shipped Claude-backed roles through a native
  runner implementation
- persistent Claude sessions are reused across eligible workflow steps
- runner failures are normalized into durable run and event history
- docs and validation have been rolled forward to the Codex runner sprint

## Follow-ups

- implement `sprint-07-codex-runner`
- add runner/backend compatibility validation once both native backends exist
