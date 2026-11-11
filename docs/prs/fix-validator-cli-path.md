# fix/validator-cli-path

## Summary

The repository validator required `foreman/cli.py`, which slice 5 turned into
the package `foreman/cli/`. The slice 5 merge reached `main` with the
validator failing: its failure line was printed and the commit step ran
anyway.

## Scope

`scripts/repo_validation.py` requires `foreman/cli/__init__.py`,
`foreman/cli/parser.py`, `foreman/engine/__init__.py` and
`foreman/store/__init__.py`.

## Files changed

- `scripts/repo_validation.py`

## Migrations

None.

## Risks

None.

## Tests

`scripts/validate_repo_memory.py`, `tests/test_repo_validation.py`, full
suite.

## Acceptance criteria satisfied

The validator passes on `main`.

## Follow-ups

Merge steps stop when the validator fails (the command chain now uses `&&`).
