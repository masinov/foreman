# PR Summary: fix/needs-you-row-edges

## Summary

- "Needs you" rows no longer add the table's edge padding to the tinted
  surface's own (owner, 2026-11-17: "the rows have padding on the sides").

## Scope

- Two rules in `frontend/src/styles/lists.css`, and a test of them.

## Files changed

- `frontend/src/styles/lists.css`, `frontend/src/pages/project/ProjectPage.test.jsx`,
  `CHANGELOG.md`, `docs/STATUS.md`

## Migrations

- none

## Risks

- none known

## Tests

- Frontend lint, tests and build. Measured in a browser on a copy of the
  live database, on the project page and the workspace.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A row's words and its button line up with the line between rows, inside
  the surface's own padding, as in `02-project-sprints.html`.

## Follow-ups

- none
