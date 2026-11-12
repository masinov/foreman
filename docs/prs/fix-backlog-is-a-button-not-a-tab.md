# fix/backlog-is-a-button-not-a-tab

## Summary

The owner: "now it is a button that links to a page when it is between two
tabs". The rule this settles: a tab changes what the page shows; a control
that goes to another page is a button or a link, and is not in the tab row.

## Scope

`pages/project/ProjectLayout.jsx`: "Backlog" (icon, count) and "Project
settings" are bordered buttons in a "Project pages" group at the top right
of the title row. The tab row is Sprints and Activity.

## Files changed

One component, one stylesheet, one test, changelog.

## Migrations

None.

## Risks

This is the fourth place the backlog entry has been in one evening. It is
the first that follows one rule.

## Tests

`npm --prefix frontend test` (336 pass). Frontend only. Seen in a screenshot.

## Follow-ups

None.
