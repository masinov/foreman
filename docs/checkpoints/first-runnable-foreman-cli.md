# Checkpoint: first-runnable-foreman-cli

## What works

- `pyproject.toml` defines the first Foreman package metadata and console entry
  point
- `./venv/bin/pip install -e . --no-build-isolation --no-deps` succeeds in the
  repo venv
- `./venv/bin/foreman --help` exposes the spec-aligned CLI shell
- `./venv/bin/foreman projects` and `./venv/bin/foreman status` return stable
  bootstrap output
- smoke tests cover the editable-install path and console entrypoint wiring
- `scripts/reviewed_codex.py` now continues after approved slices instead of
  terminating the autonomous run immediately

## What is incomplete

- the CLI still uses placeholder responses because the SQLite store slice has
  not landed yet
- role, workflow, orchestrator, scaffold, and runner modules are placeholders
- build-isolated installs would still depend on the declared packaging tools
  being available to the environment
- automatic merge continuation still depends on the approved branch being
  recoverable when the worktree is dirty

## Known regressions

- none

## Schema or migration notes

- none

## Safe branch points

- `feat/cli-package-bootstrap` after package scaffold, CLI shell, tests, and
  repo-memory updates
