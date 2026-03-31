# Sprint 30: Wire dead dashboard surfaces

- Sprint: `sprint-30-wire-dead-surfaces`
- Status: done
- Branch: `feat/sprint-30-wire-dead-surfaces`
- Goal: wire the most visible dead surfaces in the dashboard — Stop agent button,
  sprint lifecycle transitions, task field exposure (description, priority), and
  complete run serialization

## Summary

Addressed the top items from the sprint-30 gap analysis. All changes are
end-to-end: service layer, FastAPI transport, API client, and React frontend.

**Stop agent** — `POST /api/projects/{id}/agent/stop` marks every in-progress
task in the active sprint as `blocked` with a "Stop requested from dashboard"
reason and emits a `human.stop_requested` event per task. The Stop agent button
in the sprint view header is now wired to this endpoint and disabled while an
action is pending.

**Sprint lifecycle transitions** — `PATCH /api/sprints/{sprint_id}` accepts a
`{"status": "..."}` body and validates it against the allowed transition table
(`planned→active`, `planned→cancelled`, `active→completed`, `active→cancelled`).
Transitioning to `active` sets `started_at`; transitioning to `completed` or
`cancelled` sets `completed_at`. Invalid paths return 400. The sprint view
header shows a status badge and contextual action buttons (Start sprint /
Complete sprint). Sprint list cards have Start / Complete / Cancel buttons.

**Task field updates** — `PATCH /api/tasks/{task_id}` accepts `description`
and `priority`; all other fields are rejected with 400. The task detail drawer
now surfaces a Description section and a Priority row in the Details section
when those fields are non-default.

**Run serialization** — `get_task()` now includes `session_id`, `branch_name`,
`started_at`, and `completed_at` on each run record. These were present in the
`Run` model but absent from the API response.

**E2E test fixes** — Two pre-existing E2E regressions from the dashboard visual
overhaul session were repaired: `test_sprint_card_navigates_to_board` was
scoped to `.col-title` to avoid a strict-mode collision with the `detail-status`
span; `test_task_detail_shows_title` was updated from `.detail-title` (which
never existed) to `h2`.

## Deliverables

- `DashboardService.transition_sprint()` + `PATCH /api/sprints/{sprint_id}`
- `DashboardService.update_task_fields()` + `PATCH /api/tasks/{task_id}`
- `DashboardService.stop_agent()` + `POST /api/projects/{id}/agent/stop`
- Extended run serialization in `DashboardService.get_task()`
- `description` and `priority` in `get_task()` and `list_sprint_tasks()` responses
- `transitionSprint`, `updateTask`, `stopAgent` in `frontend/src/api.js`
- Sprint status badge + transition buttons in sprint view header (`App.jsx`)
- Start/Complete/Cancel action buttons on sprint list cards (`components.jsx`)
- Description section + Priority field in `TaskDetailDrawer` (`components.jsx`)
- CSS for `.sprint-status-badge`, `.btn-secondary`, `.sc-main`, `.sc-actions`,
  `.sc-action-btn`, `.sc-action-danger` in `styles.css`
- 10 new tests in `DashboardSprintLifecycleTests` in `tests/test_dashboard.py`
- 2 E2E test fixes in `tests/test_e2e.py`

## Files changed

- `foreman/dashboard_service.py`
- `foreman/dashboard_backend.py`
- `frontend/src/App.jsx`
- `frontend/src/api.js`
- `frontend/src/components.jsx`
- `frontend/src/styles.css`
- `foreman/dashboard_frontend_dist/` (rebuilt)
- `tests/test_dashboard.py`
- `tests/test_e2e.py`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-30-wire-dead-surfaces.md`
- `docs/STATUS.md`

## Tests

- 10 new tests in `DashboardSprintLifecycleTests`
- 2 E2E test fixes
- 213 non-E2E tests pass; 20 E2E tests pass; no regressions

## Risks

- Stop agent does not send a signal to the running orchestrator process; it
  marks tasks blocked so the next `select_next_task()` iteration returns nothing.
  A currently-executing agent step will run to completion before the stop takes
  effect.
- Sprint transitions do not validate task state (e.g. completing a sprint that
  still has in-progress tasks is not blocked at the API level).

## Follow-ups

- Sprint creation modal inline task entry
- Task cancellation UI
- Task dependencies display (`depends_on_task_ids`)
- Event log load-more pagination
- Sprint status filter for `cancelled` in sprint list
