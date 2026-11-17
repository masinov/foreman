# PR Summary: feat/answers-in-plain-sight

## Summary

- A task's actions are buttons where they apply, Close ends a task by hand,
  and More holds only what is rare; a blocked task's "Needs you" row says
  why and has Unblock (ADR-0030, agreed with the owner 2026-11-17).

## Scope

- Dashboard frontend, and one field added to the needs-you payload.

## Files changed

- `frontend/src/pages/task/TaskActions.jsx`, `CloseTaskDialog.jsx` (new)
- `frontend/src/pages/shared/NeedsYou.jsx`
- `frontend/src/styles/task.css`, `lists.css`, `tokens.css`
- `foreman/dashboard_overview.py`
- tests: `TaskPage.test.jsx`, `ProjectPage.test.jsx`,
  `WorkspacePage.test.jsx`, `testing/workspaceFixture.js`,
  `tests/test_dashboard_workspace_api.py`
- `docs/adr/ADR-0030-a-tasks-answers-are-in-plain-sight.md`,
  `docs/adr/README.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- Unblock from a list is one press with no confirmation, as it already was
  on the task page.
- A task in progress shows neither Run next nor Stop until the engine's
  state has been read.

## Tests

- ruff; the Python suite; frontend lint, 435 tests, build.
- In a browser on a copy of the live database: the blocked row on the
  project page and the workspace, at desktop and phone width, with a short
  and a long reason; Unblock from the row; the header of a queued, blocked,
  waiting-for-approval, backlog, finished and running task (the last with a
  step and an engine faked in the copy, where the API was also seen to
  refuse a cancel); Close with nothing chosen, as already done and as not
  needed; Reopen.
- Not seen: Stop pressed on a task a real engine is running.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- No action a person needs in a task's state is behind More.

## Follow-ups

- Whether Block should exist on a running task; Decline and Cancel in the
  backlog.
