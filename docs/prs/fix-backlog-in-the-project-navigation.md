# fix/backlog-in-the-project-navigation

## Summary

After the backlog link moved to the project's title row, the owner asked how
to get to the backlog at all: a quiet link at the top right was not found.

## Scope

`pages/project/ProjectLayout.jsx`: "Backlog" with its count is listed in the
row under the project header, between Sprints and Activity, where it was
looked for. It links to the backlog's own page (title "Backlog", breadcrumb
"Project / Backlog"), which is unchanged. The title-row link is removed.

## Files changed

One component, one test, changelog.

## Migrations

None.

## Risks

The row now holds two views of the project page and one link to another
page. They look the same. If that reads as inconsistent, the row should
become plain project navigation on every project page, the backlog included.

## Tests

`npm --prefix frontend test` (309 pass). Frontend only; the Python suite was
not re-run.

## Follow-ups

None.
