# PR Summary: fix/roles-test-model-id

## Summary

- `tests/test_cli.py` asserted the code reviewer's old model id; the role
  refresh in `chore/sprint-56-open` changed it and only `test_roles.py` was
  run before that merge.

## Scope

- One assertion.

## Files changed

- `tests/test_cli.py`

## Migrations

- none

## Risks

- none

## Tests

- `python -m unittest discover -s tests -p 'test_cli.py'`: pass

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The suite passes on `main` again.

## Follow-ups

- Run the whole suite before every merge, including docs-and-config ones.
