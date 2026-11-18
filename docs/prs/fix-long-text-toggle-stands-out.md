# PR Summary: fix/long-text-toggle-stands-out

## Summary

- The control that folds and unfolds a long text no longer looks like a
  line of that text (owner, 2026-11-17).

## Scope

- `frontend/src/ui/LongText.jsx` and its rule in `styles/ui.css`.

## Files changed

- `frontend/src/ui/LongText.jsx`, `frontend/src/ui/LongText.test.jsx`,
  `frontend/src/styles/ui.css`, `CHANGELOG.md`, `docs/STATUS.md`

## Migrations

- none

## Risks

- none known

## Tests

- Frontend lint, tests and build. Looked at in a browser on a task with a
  long description, folded and open.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The control is gold, has a caret, and differs from the text in size and
  weight.

## Follow-ups

- none
