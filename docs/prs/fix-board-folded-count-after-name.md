# PR Summary: fix/board-folded-count-after-name

## Summary

- On a folded board column the count sat next to the caret. It now follows
  the name, read downwards, as it follows the name in an open column's
  heading (owner, 2026-11-18). The caret stays alone on the rule, which is
  level with the open headings' rule.

## Scope

- `frontend/src/pages/sprint/TaskBoard.jsx`, `frontend/src/styles/sprint.css`,
  `CHANGELOG.md`

## Files changed

- the above, and this file

## Migrations

- none

## Risks

- none

## Tests

- Frontend lint, tests and build. In a browser on a copy of the live data:
  the strips show the caret, then the name with its count; the seven rules
  are at the same height (measured).

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- On a folded column the count follows the name.

## Follow-ups

- none
