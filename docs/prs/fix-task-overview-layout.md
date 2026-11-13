# fix/task-overview-layout

## Summary

On a task's Overview the long text was in the narrow column and the short
controls in the wide one: a filed description ran for several screens at
380px beside an empty column, and the three override controls were 370px
wide. The two are swapped.

## Scope

- Description and Acceptance criteria follow Checks in the wide column, at
  a line length of at most 84 characters.
- Text longer than twelve lines is folded, with "Show all" / "Show less"
  under it (`frontend/src/ui/LongText.jsx`). Short text gets no control.
- Overrides for this task sits under Details in the side column; a label
  and its control share the row evenly, and the block keeps the side
  column's width where the column is stacked under the page.
- ADR-0020 records the departure from `05-task-overview.html`.

## Files changed

`frontend/src/pages/task/OverviewTab.jsx`, `frontend/src/ui/LongText.jsx`
and its test, `frontend/src/styles/{task,ui,tokens}.css`,
`frontend/src/pages/task/TaskPage.test.jsx`, `CHANGELOG.md`,
`docs/adr/ADR-0020-dashboard-design-v7-and-frontend-structure.md`.

## Migrations

None.

## Risks

Whether a text folds is measured in the browser, so the unit test states
the heights; the real behaviour was checked by screenshot.

## Tests

`ruff`, the Python suite, `npm --prefix frontend run lint`,
`npm --prefix frontend test`, `npm --prefix frontend run build`;
screenshots of FOR-40 at 1440, 900 and 390 wide, folded and opened, with
`scripts/dashboard_shot.mjs`.

## Follow-ups

None.
