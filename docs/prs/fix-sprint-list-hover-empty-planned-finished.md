# fix/sprint-list-hover-empty-planned-finished

## Summary

Three things the owner reported on the project's Sprints tab.

## Scope

- Row hover: the highlight was exactly as wide as the row's content, so a
  status dot in the first cell touched its edge. Table containers get 8px of
  room on each side and the highlight bleeds into it; content does not move.
  Applies to every table.
- "Planned: None. When the active sprint is finished, Foreman stops until a
  sprint is planned." read like a placeholder. Removed; an active sprint
  with nothing planned is shown on its own.
- Finished sprints: the list said "The 10 most recent" with no total and a
  quiet "Show 10 more", which read as if older sprints could only be found
  by typing their name. It now says "Showing 10 of N, newest first", offers
  "Show n more" as a normal button and "Show all N", and the filter's
  placeholder says what it matches.

## Files changed

`frontend/src/pages/project/SprintsTab.jsx`, `FinishedSprints.jsx`, styles,
one test file, changelog.

## Migrations

None.

## Risks

The hover change is CSS only and was not seen in a browser: a headless
screenshot cannot hover, and embedding the page to force the state is
refused by the dashboard's own origin guard. The other two were seen in a
screenshot.

## Tests

`npm --prefix frontend test` (274 pass). Frontend only; the Python suite was
not re-run.

## Follow-ups

The engine no longer says anywhere that it stops when the active sprint
finishes with nothing planned. The engine row's sentence is the place for
that, when it is true.
