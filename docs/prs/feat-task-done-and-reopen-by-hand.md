# feat/task-done-and-reopen-by-hand

## Summary

A person can close a task by hand and reopen a closed one. Before, a task
whose work was merged outside the engine stayed "in progress" for good
(FOR-38), and a cancelled task could not come back.

## Scope

- `Mutations.complete_task(task, reason)`: `todo`, `in_progress` or
  `blocked` becomes `done`; refused in the backlog, for closed tasks and
  while an engine runs the task. Records `human.task_completed` with the
  reason, the status and the step it came from. The worktree is left alone
  (it may hold uncommitted work).
- `Mutations.reopen_task(task)`: `done` or `cancelled` becomes `todo`, the
  workflow starts over; refused when the task's sprint is finished.
  Records `human.task_reopened`.
- API: `POST /api/v1/tasks/{id}/complete` (`reason`, `requested_by`) and
  `POST /api/v1/tasks/{id}/reopen`. `GET /tasks/{id}` gains
  `closed_by_hand: {reason, by, at} | null`.
- CLI: `foreman task done <id> --reason`, `foreman task reopen <id>`.
- Dashboard: "Mark done" (reason required) and "Reopen" in the task's More
  menu; Details shows "Marked done: By hand …, not checked by Foreman" with
  the reason. Stop is offered only while an engine is running the task;
  otherwise an unfinished task offers Run next.

## Files changed

`foreman/mutations.py`, `foreman/dashboard_service.py`,
`foreman/dashboard/routers/tasks.py`, `foreman/cli/tasks.py`,
`tests/test_mutations.py`, `tests/test_dashboard_task_block.py`,
`frontend/src/api/tasks.js`, `frontend/src/pages/task/{TaskActions,OverviewTab}.jsx`,
`frontend/src/pages/task/TaskPage.test.jsx`, `docs/MANUAL.md`,
`docs/STATUS.md`, `docs/sprints/backlog.md`, `CHANGELOG.md`.

## Migrations

None. Two new event types, no schema change.

## Risks

- Mark done verifies nothing by design; the task page says so.
- Reopening a task the engine merged runs its workflow again on a branch
  that is already in the default branch.
- The manager's proposal vocabulary (ADR-0022) does not include the two
  operations; a manager cannot propose them yet.

## Tests

`ruff`, the Python suite, frontend lint, tests and build; the menu and the
Details row checked by screenshot on a copy of the project database.

## Follow-ups

- Add "mark done" and "reopen" to the manager's proposal vocabulary.
