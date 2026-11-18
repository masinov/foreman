# PR Summary: feat/board-columns-fold

## Summary

- With many workflow steps, a sprint's board became wide and hard to read.
  A finished sprint showed every step as an empty column beside Done. Board
  columns now fold to a strip (owner, 2026-11-18). This is how Trello,
  YouTrack and Linear handle it, and what Jira's request JRACLOUD-85706 asks
  for.

## Scope

- `TaskBoard.jsx`:
  - a fold caret at the end of each column's heading;
  - a folded column is a button strip (caret, count, name read downwards);
  - an empty column starts folded;
  - choices are remembered per project in `localStorage`.
- `Caret` gains `left`.
- Styles in `sprint.css` and the `--board-column-folded-width` token.

## Files changed

- `frontend/src/pages/sprint/TaskBoard.jsx`, `SprintLayout.jsx`,
  `SprintPage.test.jsx`
- `frontend/src/ui/Caret.jsx`, `frontend/src/styles/sprint.css`, `ui.css`,
  `tokens.css`
- `docs/STATUS.md` (design difference), `CHANGELOG.md`

## Migrations

- none

## Risks

- A column a person folded stays folded when tasks arrive in it. Its count
  shows them, gold when one needs the person.

## Tests

- Frontend lint, tests (450) and build. In a browser on a copy of the live
  data: Assay's finished sprint, with the empty steps folded and Done open;
  every column folded; a column opened; the rule under each folded strip
  level with the open headings.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A column folds and opens. A folded column shows its name and count, gold
  when a task in it needs you. An empty column starts folded, and the
  choice is remembered per project.

## Follow-ups

- "Fold all" and "open all", if wanted.
