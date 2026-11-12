# PR Summary: feat/task-sprint-page-list-and-board

## Summary

- The sprint page, `/dashboard/sprints/{id}` (list) and `/dashboard/sprints/{id}/board`, built from live data to `04-sprint-list.html` and `07-sprint-board.html`.
- The engine below project level is a menu in the top bar (Start, Pause or Resume, Stop), sharing one module with the project page's engine row.
- Four small API additions the page needed, so nothing on it is invented.

## Scope

- Breadcrumb: Workspace / project (link, with its needs-you count) / sprint.
- Head: title, goal, Edit (dialog), Activate (planned) or Finish (active); refusals show the API's sentence.
- Summary row: state and since when, task counts, spend and tokens, "Foreman picks its own tasks".
- Tasks: List | Board toggle as two links. List order: waiting for a person, running, queued in run order, done. Board columns come from the project's workflow (Queued, one per step, Done); Approve on rows and cards that wait for a merge approval.
- Add from backlog dialog (accepted backlog tasks, planned into this sprint through the backlog API).
- Activity: finished steps, newest first, 25 at a time with "Earlier steps".
- API: `GET /projects/{id}/workflow` (steps in definition order); sprint payload gains `started_at`, `completed_at`, `picks_own_tasks` (the project's task selection mode); sprint tasks gain `checks` (`tests`, `review`, `commit` from the completion evidence); `GET /sprints/{id}/events` accepts `type` (repeatable) so the page asks only for `workflow.step_completed`.

## Files changed

- `foreman/dashboard_service.py`, `foreman/dashboard/routers/{projects,sprints}.py`, `foreman/store/events.py`: the API additions.
- `frontend/src/pages/sprint/*`: the page (layout, head, edit dialog, list, board, checks, activity, add-from-backlog dialog, stage and column logic).
- `frontend/src/pages/shared/engineControl.js` (commands and state, shared), `EngineMenu.jsx` (top bar), `pages/project/EngineRow.jsx` (now uses the shared hook).
- `frontend/src/app/{App,Breadcrumb,pages}.js*`, `frontend/src/api/{sprints,projects}.js`, `frontend/src/ui/format.js`, `frontend/src/styles/{sprint,shell}.css`.
- Tests: `frontend/src/pages/sprint/SprintPage.test.jsx`, `frontend/src/testing/sprintFixture.js`, `tests/test_dashboard_workspace_api.py`.
- `foreman/dashboard_frontend_dist/`: rebuilt bundle.

## Migrations

- none

## Risks

- The top bar's engine menu reads the workspace payload and reloads it after a command; the breadcrumb's needs-you count is read once and is not refreshed after an approval on this page (live updates are a later slice).
- The board puts a running or blocked task whose step is not in the workflow into an extra "Elsewhere" column (shown only then); cancelled tasks are not on the board and a line says how many.
- No real browser on the development host: layout is checked in jsdom only; the look needs a person's eye.

## Tests

- `npm --prefix frontend test`: 28 files, 225 tests pass (31 new for this page).
- `npm --prefix frontend run build`: bundle rebuilt and committed.
- `./venv/bin/python -m unittest discover -s tests`: see the completion summary.
- No dependency added.

## Screenshots or output examples

- n/a (no browser on the host).

## Acceptance criteria satisfied

- Both routes render from live data; the toggle is two links and the rest of the page is identical (tested).
- Board columns come from the workflow; a test uses a workflow with different steps and sees different columns.
- List order as specified; Approve on a row or card calls the endpoint and reloads (tested).
- Edit, Activate, Finish and Add from backlog call the right endpoints and show refusals (tested).
- Engine menu and engine row share `pages/shared/engineControl.js`.

## Follow-ups

- Activity lines say the step and its result ("Test, Success"). The design's richer sentences ("Approved by sonnet-5-5 in 7 s", "Committed b232eb1, +118 −7") need the step event to carry the reviewer, duration and diff size; not recorded there today.
- The design's Done rows show "merged · commit"; the task payload has no merged marker, so done rows show the same checks as other rows.
- Refresh the breadcrumb's needs-you count after an approval (arrives with live updates).
