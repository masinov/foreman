# PR Summary: fix/paged-lists-collapse

## Summary

- A list that loads more on request had no way back to its first page
  (owner, 2026-11-17, on the sprint's Activity). All such lists now have
  "Show fewer".

## Scope

- `ui/ListPager.jsx` (new), `api/usePagedList.js` (`collapse`, `expanded`),
  and the six lists that page.

## Files changed

- `frontend/src/ui/ListPager.jsx`, `frontend/src/api/usePagedList.js`
- `frontend/src/pages/sprint/SprintActivity.jsx`, `AddFromBacklogDialog.jsx`,
  `pages/project/ActivityTab.jsx`, `BacklogTab.jsx`, `FinishedSprints.jsx`,
  `pages/task/ActivityTab.jsx`
- `frontend/src/styles/lists.css`
- tests: `pages/sprint/SprintPage.test.jsx`, `api/usePagedList.test.jsx`
- `CHANGELOG.md`, `docs/STATUS.md`

## Migrations

- none

## Risks

- none known

## Tests

- Frontend lint, 441 tests, build. In a browser on a copy of the live
  database: a sprint's Activity opened twice and put back.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- "Show fewer" is beside "Earlier steps" in the middle of the list and
  alone at its end, and returns the list to its first page.

## Follow-ups

- none
