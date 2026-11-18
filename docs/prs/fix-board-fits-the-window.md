# PR Summary: fix/board-fits-the-window

## Summary

- Owner, 2026-11-18: with columns opened, the ones past the right edge
  looked as if they had disappeared. The sideways scrollbar sat under the
  tallest column, below the window. The owner's two fixes are built:
  1. The board is never taller than the window below where it starts. A
     column with more cards scrolls them under its heading, as Trello's
     lists do, so the scrollbar is always in view.
  2. An edge where columns are cut off fades out, and the fade appears only
     on a side where something is hidden.
- Not built, by agreement: a "focused" column that widens. Folding already
  gives the room.

## Scope

- `TaskBoard.jsx`: `useBoardFit` measures where the board starts, and the frame gets
  `--board-height`, and tracks whether columns are cut off on either side
  (on scroll, window resize and `ResizeObserver`).
- `sprint.css`: `.board-frame` with the fades; each column is capped at
  `--board-height`, and its cards scroll.

## Files changed

- `frontend/src/pages/sprint/TaskBoard.jsx`, `SprintPage.test.jsx`
- `frontend/src/styles/sprint.css`, `tokens.css`
- `docs/STATUS.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- In a window shorter than about 320px below the board's start, the board
  keeps 320px and the page scrolls.

## Tests

- Frontend lint, tests and build. In a browser on a copy of the live data,
  Foreman's sprint 58 (20 cards in Done), in a 1440x800 window:
  - the board ends at 784px, inside the window;
  - Done scrolls its cards;
  - the right edge fades while columns are cut off there, and the left edge
    fades once scrolled to the end.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The sideways scrollbar is in view without scrolling the page. A hidden
  column is announced by a fade at that edge.

## Follow-ups

- "Fold the others" on a column's heading, if folding one by one becomes
  tedious.
