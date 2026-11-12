# fix/breadcrumb-names-the-project-tab

## Summary

The owner clicked "Backlog" in a task's breadcrumb ("Foreman / Backlog /
FOR-43") and expected to land on "Foreman / Backlog". The link went to the
right place, the project's Backlog tab, but the breadcrumb there said only
"Foreman", and everything above the tab row is the same on every tab.

## Scope

`app/Breadcrumb.jsx`: on the project's Backlog and Activity tabs the
breadcrumb is the project switcher followed by the tab's name as the current
step. The Sprints tab, the project's first page, stays the project alone.

## Files changed

`frontend/src/app/Breadcrumb.jsx`, one test, changelog.

## Migrations

None.

## Risks

None known.

## Tests

`npm --prefix frontend test` (279 pass). Frontend only; the Python suite was
not re-run. Seen in a magnified screenshot of the bar.

## Follow-ups

Arriving on a tab from a link still shows the project header first; the tab's
content is below it.
