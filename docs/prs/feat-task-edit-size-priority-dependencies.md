# PR Summary: feat/task-edit-size-priority-dependencies

## Summary

- Sprint 59, slice 10. A task's size, priority and dependencies can be
  changed after it is filed, from the dashboard and the CLI.

## Scope

- `Mutations.edit_task` accepts `complexity` and `depends_on_task_ids`
  (priority was already accepted and had no control). Dependencies are
  checked: each exists, is in the same project, is not the task itself and
  does not already wait for the task, directly or through others. They can
  change only while the task is `triage` or `todo`; sending back what a
  started task already waits for is not a change and is accepted.
- `foreman task edit <id>` with `--title`, `--size`, `--priority`,
  `--depends-on` (repeatable; replaces the list) and `--no-dependencies`.
- Edit task dialog: Size and Priority side by side; "Make it wait for
  other tasks" for a sprint's task that has not started, listing the
  sprint's unfinished tasks and whatever it already waits for.
- The checklist is one component (`pages/shared/WaitsFor.jsx`) used by the
  New task and Edit task dialogs.

## Files changed

- `foreman/mutations.py`, `foreman/cli/tasks.py`
- `frontend/src/pages/task/EditTaskDialog.jsx`,
  `frontend/src/pages/shared/WaitsFor.jsx` (new),
  `frontend/src/pages/project/NewTaskDialog.jsx`,
  `frontend/src/api/tasks.js`, `frontend/src/styles/ui.css`
- `tests/test_task_edit.py` (new),
  `frontend/src/pages/task/TaskPage.test.jsx`
- `docs/MANUAL.md`, `docs/STATUS.md`, `docs/sprints/current.md`,
  `docs/sprints/backlog.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- A dependency on a task in another sprint of the same project is allowed,
  as it is at creation; the dialog only offers the task's own sprint.
- The manager cannot propose these fields yet (`edit_task` in a proposal
  takes title, type, description, criteria and priority).

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1397 tests, 5 skipped)
- `npm --prefix frontend run lint`, `test` (380 tests), `run build`
- Looked at the dialog with `scripts/dashboard_shot.mjs` at 1440 and 390
  wide, on a copy of the database with a queued sprint of three tasks.

## Screenshots or output examples

- `foreman task edit t1 --size large --priority 2 --depends-on a` prints
  "Size: large | Priority: 2" and "Waits for: a".

## Acceptance criteria satisfied

- Size, priority and dependencies can each be changed and cleared after
  filing; a loop is refused with the reason, on every surface.

## Follow-ups

- Size and dependencies in the manager's `edit_task` proposal.
