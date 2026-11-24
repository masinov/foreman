# PR Summary: feat/task-a-task-an-agent-filed-names-the-task-it-came-fro

## Summary

- A task an agent filed says which task the agent was working on, on its Overview and in `foreman task show`.

## Scope

- `task_filed_from` (services/views.py) reads the filing event's `filed_from_task_id` / `filed_from_run_id`; served as `filed_from` on the task detail and in `history`.
- Overview, Details › Filed by: "the developer while working on FOR-12", linked to that task's Activity with the filing run picked; "a task that no longer exists" when it is gone. `filedBy` now says "the developer" for `agent:developer`.
- User- and system-filed tasks show nothing new.

## Files changed

- `foreman/services/views.py`, `tasks.py`, `reports.py`, `foreman/cli/tasks/reads.py`
- `frontend/src/pages/task/OverviewTab.jsx`, `taskWords.js`, `TaskPage.test.jsx`
- `tests/test_task_filed_from.py`; `docs/MANUAL.md`, `CHANGELOG.md`, `docs/sprints/*`

## Migrations

- none

## Risks

- Tasks filed before the payload existed show nothing. The design README does not list Details facts, so it is unchanged.

## Tests

- Service, API, CLI: `tests/test_task_filed_from.py`; frontend: `TaskPage.test.jsx` (link and gone cases).

## Screenshots or output examples

- `Filed by the developer while working on FOR-12`

## Acceptance criteria satisfied

- All; see tests.

## Follow-ups

- none
