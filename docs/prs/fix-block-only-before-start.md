# PR Summary: fix/block-only-before-start

## Summary

- Block overlapped with Stop and Close on a started task. The owner decided
  (2026-11-18) that Block only makes sense for a task that has not started.

## Scope

- The rule in `Mutations.block_task` (used by the API, the CLI and the
  manager's `block_task` operation) and the task page's `actionsFor`.

## Files changed

- `foreman/mutations.py`
- `frontend/src/pages/task/TaskActions.jsx`
- tests: `tests/test_mutations.py`, `tests/test_proposals.py`,
  `frontend/src/pages/task/TaskPage.test.jsx`
- `docs/adr/ADR-0030-a-tasks-answers-are-in-plain-sight.md`, `docs/MANUAL.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- A blocked task can no longer be blocked again to change its reason. It is
  unblocked or closed instead.

## Tests

- ruff, the full Python suite, frontend lint, tests and build.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- More on a running task is gone. On a task left part-way it holds Delete
  only. On a queued task it holds Block, Split and Delete.
- Blocking anything but a planned `todo` task is refused, with the reason.

## Follow-ups

- none
