# PR Summary: feat/sprint-page-top

## Summary

- The top of the sprint page, as agreed with the owner from mockup v4
  (2026-11-21): the title row; the goal (four lines, then "Show all") beside
  Details (state, tasks, spend); two tabs, Tasks and Activity, each with its
  controls on the tab line.
- Activity is the log alone, at `/dashboard/sprints/{id}/activity`, with a
  By filter (Everyone, each role present, Foreman, Users) beside All |
  Problems.
- By names the role, with the model on hover, on every activity list and on
  a task's Steps.
- The outcome line is off the sprint and project pages (ADR-0034
  amendment). The numbers stay in the CLI and API; a statistics view is in
  the backlog.

## Scope

- API: `GET /sprints/{id}/activity?by=<role|foreman|user>`; each item has
  `who`, and the response lists every `who` in the sprint's activity
  (whatever the filters) so the page can offer them.
- `foreman/domain/activity.py` says how `who` is told (`WHO`): a person's
  backends and roles, the engine's backends and the built-in role prefix.
  The frontend's `runRole` names the same split in words.
- `Tabs` takes `controls` (on the tab line) and an item's `count` and
  `current`.
- The task Overview's layout and its details list became shared classes
  (`page-overview`, `details-list`), used by the sprint's Goal and Details.
  `LongText` takes `short` (four lines).

## Files changed

- `foreman/domain/activity.py`, `foreman/store/runs.py`,
  `foreman/services/task_reads.py`, `foreman/services/task_models.py`,
  `foreman/api/routers/sprints.py`, `tests/test_dashboard_task_reads.py`
- `frontend/src/pages/sprint/{SprintLayout,SprintHead,SprintActivity,SprintPages}.jsx`
  and its test
- `frontend/src/ui/{Tabs,LongText}.jsx`, `frontend/src/app/{paths,routes,pages}.js`
- `frontend/src/pages/shared/{ActivityTable.jsx,activityWords.js}` and its test
- `frontend/src/pages/task/{ActivityTab,OverviewTab}.jsx`, `taskWords.js`,
  `TaskPage.test.jsx`
- `frontend/src/pages/project/ProjectLayout.jsx`
- Removed: `pages/shared/Outcomes.jsx` and its test, `api/outcomes.js`,
  `styles/outcomes.css`
- Styles: `ui.css`, `sprint.css`, `task.css`, `tokens.css`
- Docs: design README (Structure), ADR-0034, backlog, CHANGELOG

## Migrations

- none

## Risks

- `who` is worked out twice: in SQL for the filter, and in `runRole` for the
  words. Both use the same split (people's backends and roles, the engine's
  backends, `_builtin:` roles). A change to one must go to the other.
- A run through `api` is a user's for the filter but reads "the API" in
  words. Such runs are filings, which the activity leaves out.

## Tests

- `./venv/bin/python -m unittest discover -s tests`: 1598 tests, OK
- `ruff check`, `lint-imports`: clean
- `npx vitest run`: 469 passed; `npm run lint`, `npm run build`: clean
- Looked at on a copy of the live database at 1440 and 390 px wide: a
  finished sprint (list, Activity) and an open one (board).

## Screenshots or output examples

- `docs/prs/screenshots/feat-sprint-page-top/list.png`: a finished sprint,
  Tasks
- `docs/prs/screenshots/feat-sprint-page-top/activity.png`: its Activity
- `docs/prs/screenshots/feat-sprint-page-top/open.png`: an open sprint's
  board, with Add from backlog and New task on the tab line

## Acceptance criteria satisfied

- Goal beside Details, clamped to four lines with "Show all".
- Tasks · Activity tabs; controls on the tab line, no row under it.
- Activity shows the log only, with By and All | Problems.
- By shows the role, with the model on hover.
- No outcome line on the sprint or project page.

## Follow-ups

- In the backlog ("The sprint page, step by step"): the statistics view;
  raw output and prompt as copy and download buttons; the project page's
  tabs with their controls on the tab line; small wording frictions.
