# PR Summary: feat/activity-one-row

## Summary

- The activity views redesigned after the owner's review of the three
  slices merged the same day. Every list is one table shape with one line
  per row. Each level lists only its own things. Reasons are on hover and
  on the page a row opens.

## Scope

- `pages/shared/ActivityTable.jsx` and `styles/activity.css`: one table for
  every activity list, with fixed widths in `rem` (the class is
  `activity-table`; the project page's `.activity` section is a flex box).
- Words: `stepEvent` (sprint-level phrases naming their step), `runTook`
  (nothing under a second), people's acts by name.
- Milestones: only sprint and engine kinds (`engine_stopped` at the stop,
  `engine_lost` at the expiry). A plan with no sprint names the backlog or
  the new sprint. The task kinds and `merge_story` are removed.
- `GET /sprints/{id}/activity` replaces `/runs`: runs plus what a person
  did by hand, without bookkeeping or automatic gate decisions.
- Task Activity: the reason above the picked run. Agent side bar: one line
  per step, the reason inside the opened step.
- `usePagedList` reads again on the page's refresh, keeping rows opened with
  Earlier: project Activity no longer goes stale.
- The outcome line is one short sentence; Last change on the workspace says
  "Sprint 2 finished" with day and time and links to the sprint.

## Files changed

- Backend: `foreman/store/overview.py`, `foreman/store/runs.py`,
  `foreman/store/outcomes.py`, `foreman/domain/activity.py`,
  `foreman/domain/outcome_numbers.py`, `foreman/services/workspace.py`,
  `foreman/services/task_models.py`, `foreman/services/task_reads.py`,
  `foreman/api/routers/sprints.py`; tests
  `test_dashboard_workspace_api.py`, `test_dashboard_task_reads.py`,
  `test_outcome_numbers.py`.
- Frontend: `api/milestones.js`, `api/sprints.js`, `api/usePagedList.js`,
  `pages/shared/{ActivityTable,milestones,Outcomes,activityWords}`,
  `pages/sprint/{SprintActivity,SprintLayout}`,
  `pages/project/{ActivityTab,ProjectLayout}`,
  `pages/task/{ActivityTab,AgentPanel}`,
  `pages/workspace/{WorkspacePage,ProjectsTable}`, styles, tests and
  fixtures; `ActivityResult.jsx` removed.
- Docs: `docs/ARCHITECTURE.md`, `docs/MANUAL.md`,
  `docs/sprints/backlog.md`, `CHANGELOG.md`.

## Migrations

- none

## Risks

- `/sprints/{id}/runs` and the task milestone kinds are gone from the API;
  the dashboard was their only reader.

## Tests

- Python: the sprint activity list, milestones of sprints and engines,
  times ending in `Z`; full suite, ruff, lint-imports.
- Frontend: every list's columns and one-line rows, reasons on hover, row
  links, the Problems and Sprints/Engine filters, paged lists after a
  refresh; full suite, ESLint, build.
- Looked at every view side by side at 1440 and 390 px, on a copy of the
  database, and measured that headers and cells share their columns.

## Acceptance criteria satisfied

- One line per row, the same shape and widths on every activity list,
  titles cut the same way, each level listing its own things.

## Follow-ups

- The owner's review.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
