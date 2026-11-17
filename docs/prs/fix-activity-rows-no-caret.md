# PR Summary: fix/activity-rows-no-caret

## Summary

- The carets on a task's run rows are removed (owner, 2026-11-17): a caret says the content opens right under it, and a run's output is under the whole list.

## Scope

- `frontend/src/pages/task/ActivityTab.jsx`, its style and test.

## Files changed

- `frontend/src/pages/task/ActivityTab.jsx`, `frontend/src/pages/task/TaskPage.test.jsx`, `frontend/src/styles/task.css`, `CHANGELOG.md`

## Migrations

- none

## Risks

- none known

## Tests

- Frontend lint, tests and build.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A run's row has no caret; the picked row is shaded with its time in gold.

## Follow-ups

- Whether a run's output should open under its own row instead.
