# PR Summary: fix/needs-you-line-edge-to-edge

## Summary

- The line between "Needs you" rows runs from one edge of the tinted
  surface to the other (owner, 2026-11-17: it stopped short of the end of
  the row, unlike every other list).

## Scope

- `frontend/src/styles/lists.css`: the room at the sides moves from the
  surface to the first and last cell; the phone layout follows.

## Files changed

- `frontend/src/styles/lists.css`, `frontend/src/pages/project/ProjectPage.test.jsx`,
  `CHANGELOG.md`, `docs/STATUS.md`

## Migrations

- none

## Risks

- Differs from the design's drawing; recorded in `docs/STATUS.md`.

## Tests

- Frontend lint, tests and build. Measured in a browser on a copy of the
  live database at desktop and phone width, with rows and with none.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The line's ends are the surface's edges; the words and the button stay
  where they were.

## Follow-ups

- none
