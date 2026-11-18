# PR Summary: fix/board-column-max-width

## Summary

- With every other column folded, the one open column (Done, on a finished
  sprint) took the whole width, and its cards were page-wide for one-line
  titles (owner, 2026-11-18). Open columns still share the row, but none
  grows past 320px.

## Scope

- `frontend/src/styles/sprint.css`, `tokens.css`; `docs/STATUS.md`,
  `CHANGELOG.md`

## Files changed

- the above, and this file

## Migrations

- none

## Risks

- none

## Tests

- Frontend lint, tests and build. In a browser on a copy of the live data:
  Assay's finished sprint, with Done open on its own.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- An open column is never wider than 320px.

## Follow-ups

- none
