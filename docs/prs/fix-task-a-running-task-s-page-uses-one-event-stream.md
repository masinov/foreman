# PR Summary: fix/task-a-running-task-s-page-uses-one-event-stream

## Summary

- A running task's page held two server-sent event streams: the project's (`useLiveData`) and the sprint's (`TaskLayout`). The sprint's repeated the project's events.
- `TaskLayout` now listens through `onProjectEvent`, as `useTaskPulse` does. Same reaction: reload 300 ms after the last event about this task.

## Scope

- Task page only. The sprint page opens no stream of its own (only `useLiveData`'s), so nothing changed there.

## Files changed

- `frontend/src/pages/task/TaskLayout.jsx`, `frontend/src/pages/task/TaskPage.test.jsx`
- `docs/ARCHITECTURE.md`, `CHANGELOG.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`

## Migrations

- none

## Risks

- The reload now depends on the project's stream being open; it is, on every project page.

## Tests

- Frontend: one EventSource (the project's) with a running task; events about this task reload once per burst; events about another task do nothing. Lint, 496 tests and build pass.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- One stream on a running task's page; same reactions; tests, lint, build pass; docs updated.

## Follow-ups

- none
