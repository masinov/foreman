# PR Summary: feat/task-9405b87e253a

## Summary

- `GET /milestones` names the merge commit on `task_merged` and the merged-task count on `sprint_finished`.
- The project Activity tab and the workspace Recent list render both.

## Scope

- The engine's `engine.merge` event now records `sha` (the target branch head after the merge); `merge_branch` returns it.
- The milestone query reads `sha` from that event and counts a sprint's tasks that have a merge event.
- Frontend: the short sha in mono after a merge; "N tasks merged" after a finished sprint. The workspace table's one-line latest milestone stays short.

## Files changed

- `foreman/git.py`, `foreman/builtins.py`, `foreman/store/overview.py`, `foreman/dashboard_overview.py`
- `frontend/src/pages/shared/milestones.jsx`, `frontend/src/styles/lists.css`, `frontend/src/testing/workspaceFixture.js`
- tests: `tests/test_dashboard_workspace_api.py`, `tests/test_git.py`, `frontend/src/pages/project/ProjectPage.test.jsx`
- docs: `docs/ARCHITECTURE.md`

## Migrations

- none

## Risks

- Merges recorded before this change have no sha; they show without one (`sha` is null).
- `merged_count` counts tasks with a merge event, so a task done without an engine merge is not counted.

## Tests

- `./venv/bin/python -m unittest discover -s tests`: 1246 tests OK (1 skipped).
- `npx vitest run` in `frontend/`: 215 passed.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- `task_merged` carries `sha`, `sprint_finished` carries `merged_count`; the Activity tab and Recent list show them; tested.

## Follow-ups

- None.
