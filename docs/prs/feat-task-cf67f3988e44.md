# PR Summary: feat/task-cf67f3988e44

## Summary

- Task and sprint API payloads now carry their parents' ids, and the task payload names the policy of the human gate it waits at.
- The workspace Needs you uses that policy for its kind label ("Approve a plan" / "Approve a merge").

## Scope

- `GET /tasks/{id}` and `/sprints/{id}/tasks`: `project_id`, `sprint_id`, `gate_policy` (`plan_approval`, `merge_approval`, or null when not at a gate or the gate names no policy).
- `GET /sprints/{id}` and the project sprint list: `project_id`.
- Frontend: `api/workspace.js` carries `policy`; `NeedsYou.jsx` labels by it, falling back to the step name.

## Files changed

- `foreman/dashboard_service.py`
- `frontend/src/api/workspace.js`, `frontend/src/pages/workspace/NeedsYou.jsx`, `frontend/src/testing/workspaceFixture.js`, `frontend/src/pages/workspace/WorkspacePage.test.jsx`
- `tests/test_dashboard.py`

## Migrations

- none

## Risks

- Additive fields only; no existing field changed.

## Tests

- `tests/test_dashboard.py` (gate flag test extended for each new field); frontend vitest suite.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Task payloads include project_id, sprint_id, gate policy; sprint payloads include project_id; tests cover each; Needs you label uses the policy.

## Follow-ups

- The workspace overview still composes Needs you client-side; the server-side workspace endpoint already names `approve_plan` / `approve_merge`.
