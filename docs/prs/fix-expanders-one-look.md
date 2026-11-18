# PR Summary: fix/expanders-one-look

## Summary

- Every control that opens more in place looks the same: gold, a control's
  size and weight, a caret (owner, 2026-11-17: "same design for everything
  that expands that is similar ... either all grey or orange").

## Scope

- `ui/Caret.jsx` (new), `ui/LongText.jsx`, `ui/Disclosure.jsx`, the list
  buttons that show more, and the `expander` rule in `styles/ui.css`.

## Files changed

- `frontend/src/ui/Caret.jsx`, `LongText.jsx`, `Disclosure.jsx` and tests
- `frontend/src/pages/shared/NeedsYou.jsx`, `pages/project/SprintsTab.jsx`,
  `FinishedSprints.jsx`, `ActivityTab.jsx`, `BacklogTab.jsx`,
  `pages/task/ActivityTab.jsx`, `pages/sprint/SprintActivity.jsx`,
  `AddFromBacklogDialog.jsx`
- `frontend/src/styles/ui.css`, `motion.css`, `tokens.css`
- `CHANGELOG.md`, `docs/STATUS.md`

## Migrations

- none

## Risks

- Gold no longer means only "needs you"; recorded in `docs/STATUS.md`. The
  colour is one token, `--color-expander`.

## Tests

- Frontend lint, tests and build. Looked at in a browser on a copy of the
  live database: a task's Overview and Activity tabs and the project page.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- One look for all of them.

## Follow-ups

- none
