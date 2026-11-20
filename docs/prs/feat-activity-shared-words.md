# PR Summary: feat/activity-shared-words

## Summary

- Slice 1 of "Activity, one stream at three depths" (backlog, owner
  2026-11-21). The words for what happened come from one place
  (`frontend/src/pages/shared/activityWords.js`), every activity table names
  its columns, and every row leads to what it is about.

## Scope

- Words: who did a run (a model, Foreman, the person who filed it, a person
  at a gate); how it ended ("Sent back", "Passed", "Merged", "Closed",
  "Asked a person", "Merge conflict", "Interrupted"); why (the reviewer's or
  person's reason, a failure's message, "By the project setting").
- `formatDuration`: "4 min 22 s" instead of "261.9 s".
- Task Activity: the reason under the result; `?run=` picks a run; By names
  Foreman and the filer. Agent side bar: the same words, the reason under a
  step. Overview: "Approved after 1 send-back".
- Milestones (workspace Recent, project Activity): named columns, day and
  time, the whole row a link.
- Sprint Activity: named columns, task key and title, the row a link to the
  run on the task's Activity. Slice 2 rebuilds it on runs.
- `Table` takes `rowHref`; the router keeps the query (`useRoute().query`).
- API: `RunItem.outcome_detail` on `GET /tasks/{id}/runs`.

## Files changed

- `frontend/src/pages/shared/activityWords.js`, `ActivityResult.jsx`,
  `activityWords.test.js` (new); `frontend/src/styles/activity.css` (new)
- `frontend/src/pages/task/taskWords.js`, `ActivityTab.jsx`,
  `AgentPanel.jsx`, `Decision.jsx`, `runWords.js`
- `frontend/src/pages/shared/milestones.jsx`,
  `frontend/src/pages/sprint/SprintActivity.jsx`
- `frontend/src/ui/Table.jsx`, `format.js`; `frontend/src/app/router.jsx`,
  `paths.js`; styles `ui.css`, `manager.css`
- Tests: `Table.test.jsx`, `format.test.js`, `TaskPage.test.jsx`,
  `runWords.test.js`, `SprintPage.test.jsx`, `ProjectPage.test.jsx`,
  `WorkspacePage.test.jsx`
- `foreman/services/task_models.py`, `task_reads.py`,
  `tests/test_dashboard_task_reads.py`
- `docs/sprints/backlog.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- Milestone times depend on the viewer's time zone, as every other time on
  the dashboard does; the tests compare rows without the clock.
- A `?run=` that is not among the 25 newest runs falls back to the newest.

## Tests

- 1593 Python tests, ruff, lint-imports; 471 frontend tests, ESLint,
  build. Looked at with `scripts/dashboard_shot.mjs` on a copy of the
  database.

## Acceptance criteria satisfied

- Named columns on every activity table; rows lead to the detailed page;
  the same run reads the same on the task's Activity, Overview, the Agent
  side bar and the decision.

## Follow-ups

- Slices 2 (sprint Activity on runs) and 3 (project milestones).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
