# PR Summary: feat/workspace-defaults-from-a-terminal

## Summary

- FOR-49, developed by the engine in sprint 60c (`55b6129`, tests passed,
  review approved), was left at its merge gate 28 commits behind `main`
  while the engine was not running. Brought up to date with `main` by hand,
  checked again and merged; the task is recorded done.

## Scope

- `foreman role` and `foreman workflow` take `--workspace` in place of a
  project.

## Files changed

- `foreman/cli/definitions.py`, `tests/test_project_definitions.py`
- `CHANGELOG.md`, `docs/MANUAL.md`

## Migrations

- none

## Risks

- none known; the merge of `main` into the task's work had no conflicts.

## Tests

- ruff; `tests.test_project_definitions` (78 tests) after the merge of
  `main`; the full suite before merging.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- FOR-49's criteria, as reviewed at its gate.

## Follow-ups

- none
