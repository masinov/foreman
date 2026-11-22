# PR Summary: feat/task-steps-table

## Summary

- A task's Activity table lists the task's own steps, headed "Steps",
  from the mockup the owner chose (2026-11-22).
- It leaves out:
  - the step that closes the task after its merge;
  - engine records that do not name the task.
- An engine record that names the task (a step stopped or paused during
  it) stays, as "Interrupted".
- The rows:
  - a step tried again says "attempt 2";
  - a step that made a commit says "Committed";
  - a gate the setting decided says "Approved by setting", in no colour;
  - the Commit column names the commit each step was about.
- The picked step's Result uses the same words as its row.

## Scope

- `GET /tasks/{id}/runs` lists the task's own steps (`domain.activity`
  says which) and gives each `attempt` and `step_commit`. `step_commit` is
  the run's commit, else the `engine.test_run` head or the
  `engine.merge` commit.
- `stepOutcome` in `activityWords.js` holds the row words, which the facts
  column shares.
- `ActivityTable` takes a subject note (the attempt).
- The Overview stops counting runs, which never matched the steps listed.

## Files changed

- Server:
  - `foreman/domain/activity.py`
  - `foreman/store/runs.py`
  - `foreman/services/task_reads.py`
  - `foreman/services/task_models.py`
  - `tests/test_dashboard_task_reads.py`
- Frontend:
  - `frontend/src/pages/shared/{activityWords.js,activityWords.test.js,ActivityTable.jsx}`
  - `frontend/src/pages/task/{ActivityTab,OverviewTab}.jsx`
  - `frontend/src/pages/task/stepFacts.js`
  - `frontend/src/pages/task/TaskPage.test.jsx`
  - `frontend/src/styles/activity.css`
- Docs: `CHANGELOG.md`, `docs/sprints/backlog.md`

## Migrations

- none

## Risks

- An engine record is kept on a task when its detail names the task in
  quotes ("during task 'task-1'"), which is how the engine writes them.
  A record worded otherwise is left out; the transcript of the run it is
  on still has it.
- `attempt` counts within the list's own step name. A workflow that
  reuses a step name in two places counts them together.

## Tests

- Python: 1599 tests, OK; `ruff`, `lint-imports` clean
- Frontend: 478 passed; `npm run lint`, `npm run build` clean
- Looked at on a copy of the live database: ASS-16 (9 steps, as in the
  mockup) and FOR-18, an older task with an engine shutdown during its
  develop step.

## Acceptance criteria satisfied

- The table lists what happened to the task and nothing else.
- Attempts, commits and the row words match the mockup, except the test
  count.

## Follow-ups

- Record how many tests ran, so a Test row can say "Passed · 186 tests".
- The repository facts and the engine fixes in the backlog.
