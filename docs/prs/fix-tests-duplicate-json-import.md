# PR Summary: fix/tests-duplicate-json-import

## Summary

- CI failed on `main` at `310496e`, the merge of FOR-61:
  `tests/engine_support.py` imported `json` twice, and `ruff` (F811)
  refused it. The duplicate line is removed.
- The cause: Foreman's test step does not run the linters CI runs, so the
  merge went through. Foreman's `test_command` (a project setting in the
  database, not a file here) now begins with
  `./venv/bin/ruff check foreman tests scripts && ./venv/bin/lint-imports`.
  Recorded in `docs/sprints/current.md`.

## Scope

One test-support line, the sprint file, this note.

## Files changed

- `tests/engine_support.py`
- `docs/sprints/current.md`
- this note.

## Migrations

None.

## Risks

None.

## Tests

- `ruff check foreman tests scripts` is clean.
- The whole Python suite, run once before the merge.

## Acceptance criteria

- `ruff` is clean on `main`, and CI is green again.

## Follow-ups

- None.
