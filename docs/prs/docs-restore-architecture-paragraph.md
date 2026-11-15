# PR Summary: docs/restore-architecture-paragraph

## Summary

- Puts back a paragraph of `docs/ARCHITECTURE.md` that the merge of
  `feat/task-run-output-in-sentences` removed by mistake.

## Scope

- The edit that rewrote the `GET /runs/{id}/output` bullet also cut the 13
  lines after it ("Two writes serve the task page's More menu and
  decision ..."). They are restored from the commit before, word for word.
  The bullet also says again what the caps are.

## Files changed

- `docs/ARCHITECTURE.md`

## Migrations

- none

## Risks

- none

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`
- `diff` against the file before the faulty merge shows only the intended
  bullet changed.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The paragraph is back.

## Follow-ups

- none
