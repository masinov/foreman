# PR Summary: feat/board-panels-from-the-lab

## Summary

- The board design the owner chose after trying five variants in a
  standalone board lab (2026-11-18):
  - each column is a panel in the tinted tone, with its cards one step
    lighter (new token `--color-board-card`);
  - columns sit closer together;
  - the cut-edge fade is 24px;
  - the scrollbars are thin and grey (new `--scrollbar-size` and
    `--color-scrollbar-thumb` tokens), and a column's scrollbar sits in the
    panel's margin with room always kept for it;
  - the board is 160px taller than the room left in the window.
- Kept: 272px fixed columns, folding, empty columns folded by default, the
  fade.

## Scope

- `frontend/src/styles/sprint.css`, `tokens.css`,
  `frontend/src/pages/sprint/TaskBoard.jsx` (height)

## Files changed

- the above; `docs/STATUS.md` (differences from the design),
  `CHANGELOG.md`, this file

## Migrations

- none

## Risks

- The tinted tone now also marks board columns. The design reserves it for
  "act here". This is recorded in STATUS as the owner's choice.

## Tests

- Frontend lint, tests (451) and build. In a browser on a copy of the live
  data:
  - Foreman's sprint 58 board, 1440x860 window;
  - each column's cards are as wide as its heading (256px) with an 8px
    scrollbar margin;
  - the board ends 144px below the window;
  - Done scrolls its 20 cards inside its panel.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The dashboard's board looks as chosen in the lab.

## Follow-ups

- The lab is a claude.ai artifact, outside the repository.
