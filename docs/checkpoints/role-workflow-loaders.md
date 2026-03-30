# Checkpoint: role-workflow-loaders

## What works

- shipped `roles/*.toml` and `workflows/*.toml` files mirror the spec examples
- `foreman.roles` loads role definitions and renders prompt templates with the
  completion marker and signal documentation injected
- `foreman.workflows` loads workflow graphs and validates transitions against
  declared steps and known roles
- `foreman roles` and `foreman workflows` list the shipped definitions from the
  installed CLI

## What is incomplete

- project initialization still does not persist a project or select custom
  roles or workflows
- the orchestrator does not execute workflow steps yet
- native runners, context projection, and human-gate commands remain
  unimplemented

## Known regressions

- none identified in the validated slice

## Schema or migration notes

- no SQLite schema changes landed in this slice
- Python 3.10 validation uses a local TOML compatibility shim with a pip-vendor
  fallback during `--no-deps` installs

## Safe branch points

- `feat/role-workflow-loaders` after shipped TOML defaults, loader modules, CLI
  listing commands, tests, and sprint rollover docs
