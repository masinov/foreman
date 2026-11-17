# PR Summary: fix/activity-pick-and-settle

## Summary

- On a task's Activity tab a person can go back to any step by pressing its
  row, can see which row the output under the list belongs to, and the tab
  no longer flashes when a step is registered (owner, 2026-11-17).

## Scope

- `ui/Table.jsx` (a row can be pressed; a row can be marked as arrived),
  `pages/task/ActivityTab.jsx`, `ChangesTab.jsx`, and their styles.

## Files changed

- `frontend/src/ui/Table.jsx`, `pages/task/ActivityTab.jsx`,
  `pages/task/ChangesTab.jsx`, `pages/task/TaskPage.test.jsx`
- `frontend/src/styles/ui.css`, `task.css`, `motion.css`
- `CHANGELOG.md`, `docs/STATUS.md`

## Migrations

- none

## Risks

- After "Earlier", a re-read while the task runs returns the list to its
  first 25 runs, as before.

## Tests

- Frontend lint, 439 tests, build. In a browser on a copy of the live
  database with a running step faked in it: an earlier run picked by its
  row, then a new run inserted while the page was open; the new row arrived
  with its animation, the picked run stayed picked and shown.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Pressing a step shows its activity; the pick survives a new step; the
  list updates in place.

## Follow-ups

- Which run the tab opens on for a finished task (today the newest, which
  is the engine's closing step).
