# PR Summary: fix/board-columns-fixed-width

## Summary

- Board columns now have one width, as Trello's lists do (owner,
  2026-11-18, after comparing Trello and Jira). Every open column is 272px
  wide, and the board scrolls sideways when they do not fit. Before, columns
  shared the row between 220px and 320px.

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
  Assay's finished sprint, and an active-sprint board with several columns
  open.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Every open column is 272px wide, whatever the screen and however many
  columns are open.

## Follow-ups

- none
