# PR Summary: fix/tabs-keep-the-page

## Summary

- Changing tab redrew the whole page, twice on a task's Activity tab, and
  the page shifted slightly between tabs (owner, 2026-11-17).

## Scope

- How routes map to page components, and one line of page-wide style.

## Files changed

- `frontend/src/app/pages.js`, `App.jsx`
- `frontend/src/pages/task/TaskPages.jsx`, `pages/project/ProjectPages.jsx`,
  `pages/settings/SettingsPages.jsx`, `pages/sprint/SprintPages.jsx`
- `frontend/src/styles/base.css`
- tests: `pages/task/TaskPage.test.jsx`, `app/routes.test.js`
- `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- State held by a page's head now survives a change of tab (a notice such
  as "Saved." stays until the page changes).

## Tests

- Frontend lint, 438 tests, build. In a browser on a copy of the live
  database: the requests made when a tab is pressed, and the position of
  the page with a scrollbar and without.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Pressing a tab reads only that tab's data and leaves the head as it is.

## Follow-ups

- none
