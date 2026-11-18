# PR Summary: fix/one-guidance-box

## Summary

- Guidance for a task's agent is written in one place, which stays in view.

## Scope

- `TellAgent.jsx`: the box and the list of what was told, used by the
  Activity tab only. Pinned to the bottom of the window.
- The guidance section is removed from the Overview tab.

## Files changed

- `frontend/src/pages/task/{TellAgent,ActivityTab,OverviewTab}.jsx`,
  `styles/task.css`, `TaskPage.test.jsx`
- `docs/STATUS.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- A person who looked for guidance on Overview finds it on Activity.

## Tests

- Both suites. Measured on a copy of the live database with a step
  running: page 3036 px tall, the box at 634 to 800 of an 800 px window.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- There is one box, and it is visible without scrolling while a step runs.

## Follow-ups

- none
