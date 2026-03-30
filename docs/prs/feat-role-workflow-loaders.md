# PR Summary: feat/role-workflow-loaders

## Summary

- implement declarative role and workflow loading from disk
- ship default TOML definitions that mirror the spec examples
- expose the loaded definitions through `foreman roles` and `foreman workflows`

## Scope

- replace placeholder `foreman.roles` and `foreman.workflows` modules with real
  loader and validation logic
- add a TOML compatibility shim that works in the repo's Python 3.10 venv
- add shipped `roles/` and `workflows/` directories, loader tests, and repo
  memory updates

## Files changed

- `foreman/_toml.py`
- `foreman/roles.py`
- `foreman/workflows.py`
- `foreman/cli.py`
- `pyproject.toml`
- `roles/developer.toml`
- `roles/code_reviewer.toml`
- `roles/architect.toml`
- `roles/security_reviewer.toml`
- `workflows/development.toml`
- `workflows/development_with_architect.toml`
- `workflows/development_secure.toml`
- `tests/test_cli.py`
- `tests/test_roles.py`
- `tests/test_workflows.py`
- `README.md`
- `docs/STATUS.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `docs/checkpoints/role-workflow-loaders.md`
- `docs/prs/feat-role-workflow-loaders.md`
- `docs/sprints/current.md`
- `docs/sprints/archive/sprint-01-foundation.md`
- `docs/sprints/backlog.md`
- `CHANGELOG.md`

## Migrations

- none

## Risks

- Python 3.10 TOML loading currently depends on a local compatibility shim and
  a pip-vendored fallback during `--no-deps` validation installs
- the loader layer is real, but the orchestrator still does not execute loaded
  workflows yet

## Tests

- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile foreman/_toml.py foreman/roles.py foreman/workflows.py foreman/cli.py tests/test_cli.py tests/test_roles.py tests/test_workflows.py`
- `./venv/bin/foreman --help`
- `./venv/bin/foreman roles`
- `./venv/bin/foreman workflows`

## Screenshots or output examples

- `foreman roles` lists `architect`, `code_reviewer`, `developer`, and
  `security_reviewer`
- `foreman workflows` lists `development`,
  `development_with_architect`, and `development_secure`

## Acceptance criteria satisfied

- roles and workflows can be loaded from TOML on disk
- prompt rendering injects completion and signal metadata
- workflow transitions are validated against declared steps and known roles
- repo memory now points the next agent at the orchestrator sprint

## Follow-ups

- implement the orchestrator main loop against persisted tasks and loaded
  workflow graphs
- add built-in execution seams for test, merge, and mark-done steps
- persist project initialization and custom workflow selection through
  `foreman init`
