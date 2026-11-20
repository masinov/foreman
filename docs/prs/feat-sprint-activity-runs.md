# PR Summary: feat/sprint-activity-runs

## Summary

- Slice 2 of "Activity, one stream at three depths" (backlog, owner
  2026-11-21). The sprint page's Activity lists the runs of the sprint's
  tasks, one row per meaningful step, newest first. Each row has who did
  it, its result and reason, time and spend, and leads to that run on the
  task's Activity. A filter shows only send-backs and failures.

## Scope

- `foreman/domain/activity.py` (new): which runs only keep a record, and
  which are problems.
- `RunStore.list_sprint_runs_page`; `TaskReads.list_sprint_runs`;
  `SprintRunItem`, `SprintRuns`; `GET /sprints/{id}/runs` with `only=problems`.
- Frontend: `listSprintRuns`; `SprintActivity` rewritten on it; the old
  `listSprintEvents` client call, no longer used, removed. The engine's own
  records ("engine.sprint_ready", "Engine shutting down") read "Recorded" on
  a task's Activity, not "Interrupted".

## Files changed

- `foreman/domain/activity.py`, `foreman/store/runs.py`,
  `foreman/services/task_models.py`, `task_reads.py`,
  `foreman/api/routers/sprints.py`, `tests/test_dashboard_task_reads.py`
- `frontend/src/api/sprints.js`, `pages/sprint/SprintActivity.jsx`,
  `SprintLayout.jsx`, `SprintPage.test.jsx`, `testing/sprintFixture.js`,
  `pages/shared/activityWords.js` and its test, `styles/activity.css`
- `docs/ARCHITECTURE.md`, `docs/MANUAL.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- The list reads runs joined to tasks by sprint; Foreman's largest sprint
  has a few hundred runs.

## Tests

- ruff, lint-imports, the Python suite; ESLint, the frontend suite, build.
  Looked at on a copy of the database: Assay's sprint 2, all and problems.

## Acceptance criteria satisfied

- Each step names who did it and why it was sent back; columns are named;
  rows lead to the run; bookkeeping steps are gone; a send-backs filter.

## Follow-ups

- Slice 3: project milestones.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
