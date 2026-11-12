# PR Summary: feat/task-record-the-commit-each-run-left-so-task-steps-ca

## Summary

- Agent runs record the task branch's head when they finish (`runs.commit_sha`).
- `GET /tasks/{id}` runs and `GET /tasks/{id}/runs` return `commit_sha`.
- Overview's Steps say "Committed <sha>" (design 05); Activity has a Commit column.

## Scope

- Store, engine recording, API payloads, task page. No change to system runs
  (orchestrator, gate decisions), which have no branch work to credit.
- The recorded value is the branch head after the run, as the task asks. The
  Steps row says "Committed" only when that head differs from the previous
  run's, so a reviewer that changed nothing does not claim a commit. Activity
  shows the plain head for every run that has one.

## Files changed

- `foreman/migrations.py`, `models.py`, `store/runs.py`, `store/rows.py`
- `foreman/engine/records.py`, `engine/workflow_runner.py`
- `foreman/dashboard/task_models.py`, `dashboard_task_reads.py`, `dashboard_service.py`
- `frontend/src/pages/task/taskWords.js`, `ActivityTab.jsx`, tests and fixture
- `tests/test_store.py`, `test_dashboard_task_reads.py`, `test_engine_workflow.py`
- `CHANGELOG.md`

## Migrations

- 23: `ALTER TABLE runs ADD COLUMN commit_sha TEXT` (nullable; old runs have none).

## Risks

- Runs from before this change show no commit; their Steps rows keep the outcome.
- A run that made no commit on its first visit to a branch is shown as
  "Committed <base head>", because the head before the run is not recorded.

## Tests

- Store round trip, API (`/tasks/{id}` and `/tasks/{id}/runs`), engine workflow
  (develop run carries the commit the agent left), page (Steps and Activity).

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Runs carry the commit they left; Overview steps and Activity show it; tests on store, API and page.

## Follow-ups

- Record the head before each run too, so "Committed" can be exact on a first visit.
