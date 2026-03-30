# PR Summary: feat/cli-package-bootstrap

## Summary

- bootstrap the `foreman` Python package and `pyproject.toml`
- add a runnable CLI shell aligned to the spec's command surface
- cover the bootstrap CLI with smoke tests and update repo memory to point at
  the SQLite store slice next
- fix the reviewed Codex supervisor so approved slices continue into the next
  task instead of terminating the autonomous run

## Scope

- create the initial package scaffold and placeholder module seams
- implement `python -m foreman` plus `foreman` console-script metadata
- add smoke tests that perform an editable install and exercise `foreman --help`,
  `foreman projects`, and `foreman status`
- enhance `scripts/reviewed_codex.py` with explicit full-spec completion,
  post-approval merge handling, and continuation to the next slice
- add regression tests for the reviewed Codex continuation flow
- update validation and project-memory docs for the completed sprint task

## Files changed

- `pyproject.toml`
- `foreman/`
- `tests/test_cli.py`
- `tests/test_reviewed_codex.py`
- `scripts/reviewed_codex.py`
- `scripts/repo_validation.py`
- `README.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/TESTING.md`
- `CHANGELOG.md`
- `docs/checkpoints/first-runnable-foreman-cli.md`

## Migrations

- none

## Risks

- the CLI commands are intentionally placeholders until the SQLite store exists
- editable-install validation depends on the repo venv containing the packaging
  toolchain declared in `pyproject.toml`
- automatic merge continuation in `reviewed_codex.py` still depends on branch
  state being recoverable with sanctioned git commands when the worktree is not
  clean

## Tests

- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/foreman --help`
- `./venv/bin/foreman projects`
- `./venv/bin/foreman status`
- `./venv/bin/python -m unittest tests.test_reviewed_codex -v`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`

## Screenshots or output examples

- `foreman --help` lists the canonical spec-aligned command surface
- `foreman projects` and `foreman status` return stable bootstrap messages

## Acceptance criteria satisfied

- `pyproject.toml` exists
- the `foreman/` package scaffold exists
- the CLI entrypoint responds through `./venv/bin/foreman`
- smoke tests cover the required commands
- the reviewed Codex supervisor no longer exits immediately after one approved
  slice
- sprint and status docs now point the next agent at the SQLite store slice

## Follow-ups

- implement the SQLite models and store baseline
- replace bootstrap CLI placeholder output with real store-backed queries
- keep the repo venv packaging toolchain aligned with `pyproject.toml`
- consider adding deeper supervisor-flow tests beyond the current continuation
  regression coverage
