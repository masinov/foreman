# PR Summary: fix/task-model-override-is-a-list

## Summary

- A task's model overrides are chosen from the project's configured models
  instead of typed. Asked for by the owner.

## Scope

- `Overrides.jsx` reads the project's definitions for the list; a value the
  task already has stays choosable.
- The API still accepts any text for an override; the dashboard no longer
  offers a way to send one.

## Files changed

- `frontend/src/pages/task/Overrides.jsx`, `TaskPage.test.jsx`,
  `testing/taskFixture.js`, `CHANGELOG.md`

## Migrations

- none

## Risks

- none

## Tests

- Both suites; in a real browser on a database copy a model was chosen for
  a task's develop step and saved.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- No free-text model field is left on the task page.

## Follow-ups

- Refuse, in the API, an override model that the agent program cannot run.
