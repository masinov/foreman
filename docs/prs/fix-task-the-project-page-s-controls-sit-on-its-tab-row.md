# PR Summary: fix/task-the-project-page-s-controls-sit-on-its-tab-row

## Summary

- The project page works like the sprint page: each tab's controls sit on the tab row. A heading stays only where it marks one group off from another.

## Scope

- New sprint on the Sprints tab row; All | Sprints | Engine on the Activity tab row, through `tabLine(controls)` passed from `ProjectLayout`.
- Sprints: headings "Active and planned" and "Finished" (folded; count and latest sprint in its quiet part). `SectionHeading` gains `expanded`, `onToggle`, `controls` for its own fold.
- Activity: heading row removed; the table keeps its caption.
- Milestone table key column "About" (project Activity and workspace recent changes).
- Sprints tab count; the queue is read in `ProjectLayout` so the count shows on either tab.

## Files changed

- frontend: `pages/project/{ProjectLayout,ProjectPages,SprintsTab,ActivityTab,FinishedSprints}.jsx`, `pages/shared/milestones.jsx`, `ui/SectionHeading.jsx`, `styles/ui.css`, tests in `ProjectPage.test.jsx` and `WorkspacePage.test.jsx`
- docs: design README, `02`, `09`, `11` design files, CHANGELOG, sprint current and backlog

## Migrations

- none

## Risks

- The Finished heading's button name now reads "Finished 12 latest: ..."; anything matching the old "Finished sprints" text must change.

## Tests

- Frontend: eslint (no warnings), vitest 509 pass, vite build.

## Screenshots or output examples

- n/a (design files updated instead)

## Acceptance criteria satisfied

- Controls on the tab row; two same-kind headings with Finished folded; no Activity heading; "About"; Sprints count; behaviour unchanged; tests for each point.

## Follow-ups

- none
