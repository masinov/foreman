# fix/section-rules-and-changes-layout

## Summary

The owner's report: section titles "sit there in a void" above what they
name; the Changes tab carries figures no other tab has; inside it a verbose
line posed as a title; and picking a file showed its diff below a list of
dozens of files.

## Scope

- `ui/SectionHeading`: the heading has a rule under it spanning the section
  (`plain` opts out; used by Needs you, whose content is a tinted surface).
- Tables: the line under column headers is the faint row line.
- Task tabs: "Changes" has no figures.
- `pages/task/ChangesTab`: heading "Files" with the count and +added
  −deleted; a quiet line "<commit> compared with <branch>"; "Measured by the
  engine from git" removed (Checks says what is measured). The file list is
  a sticky column that scrolls within the window height; the diff is beside
  it. Below the width where both fit, the diff wraps under the list, which
  still scrolls on its own.

## Files changed

`frontend/src/ui/SectionHeading.jsx`, `frontend/src/pages/task/` (ChangesTab,
TaskLayout), `frontend/src/pages/shared/NeedsYou.jsx`, styles, tests,
changelog.

## Migrations

None.

## Risks

Every section heading in the dashboard changed appearance. The task
Overview and Changes tabs were seen in screenshots; other pages were not
re-checked one by one.

## Tests

`npm --prefix frontend test` (277 pass). Frontend only; the Python suite was
not re-run.

## Follow-ups

Headless Chrome with `--virtual-time-budget` never finishes on a page that
holds a live event stream (a running task). Screenshots of such pages need a
database copy where the task is not running; `docs/TESTING.md` should say so
when the fidelity pass adds its section.
