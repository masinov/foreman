# PR Summary: feat/human-gate-resume

## Summary

- implement persisted human-gate approve and deny commands
- resume paused tasks from the stored workflow step instead of restarting from
  workflow entry
- record bootstrap deferred resume state when the next step still needs a
  native runner

## Scope

- `foreman.orchestrator` human-gate decision handling and resume semantics
- `foreman.cli` approve and deny command wiring
- orchestrator and CLI coverage for pause, approve, deny, and deferred resume
- repo-memory rollover from sprint 05 to sprint 06

## Files changed

- `foreman/cli.py`
- `foreman/orchestrator.py`
- `tests/test_cli.py`
- `tests/test_orchestrator.py`
- `README.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-05-human-gates.md`
- `docs/checkpoints/human-gate-resume.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `CHANGELOG.md`

## Migrations

- none

## Risks

- CLI approval and denial can only defer agent-backed next steps until the
  native runner slice lands
- workflow prompts after human approval currently reflect the human decision
  run rather than the original planning output unless the workflow explicitly
  carries that earlier output forward

## Tests

- `./venv/bin/python -m unittest tests.test_orchestrator tests.test_cli -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python -m py_compile foreman/cli.py foreman/orchestrator.py tests/test_orchestrator.py tests/test_cli.py`
- `./venv/bin/foreman approve --help`
- `./venv/bin/foreman deny --help`

## Screenshots or output examples

- `foreman approve --help` now exposes `--db` and `--note`
- `foreman deny --help` now exposes `--db` and `--note`

## Acceptance criteria satisfied

- `foreman approve` and `foreman deny` now operate on paused human-gate tasks
- paused tasks resume from persisted workflow state instead of restarting from
  workflow entry
- approval and denial decisions are persisted with workflow and event history
- docs and validation have been rolled forward to the Claude runner sprint

## Follow-ups

- implement `sprint-06-claude-runner`
- add the native Codex runner after the Claude slice lands
