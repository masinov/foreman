# fix/backlog-link-in-the-project-title-row

## Summary

`feat/backlog-is-its-own-page` linked the backlog from a line of text under
the sprint queue. The owner found that a strange way to reach a page.

## Scope

- `pages/project/ProjectLayout.jsx`: a "Project pages" navigation in the
  title row holds "Backlog" (with an icon and its count) and "Project
  settings". Both are pages of their own, not tabs.
- `pages/project/SprintsTab.jsx`: the line under the queue is removed.
- `ui/Icon`: an `inbox` icon.

## Files changed

Two components, one icon, styles, two tests, changelog.

## Migrations

None.

## Risks

None known.

## Tests

`npm --prefix frontend test` (309 pass). Frontend only; the Python suite was
not re-run. Seen in a screenshot.

## Follow-ups

None.
