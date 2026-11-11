# PR Summary: fix/completed-sprint-delete

## Summary

- The sprint page never offered Delete for a completed sprint because it
  compared the sprint status with `"done"`; sprints are `"completed"`.

## Scope

- One comparison in `frontend/src/App.jsx`, one test, rebuilt bundle.

## Files changed

- `frontend/src/App.jsx`, `frontend/src/App.test.jsx`,
  `foreman/dashboard_frontend_dist/*`, `docs/sprints/current.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- none

## Tests

- `npm --prefix frontend test`: 54 pass (1 new); build clean

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Delete appears on a completed sprint and not on an active one.

## Follow-ups

- Statuses as shared constants in the frontend (Phase 4).
