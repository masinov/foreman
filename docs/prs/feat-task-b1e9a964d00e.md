# PR Summary: feat/task-b1e9a964d00e

## Summary

- A pending sprint-order decision gate is a fifth Needs you item, `settle_order`, on the workspace and project pages. It is accepted or rejected there, so `/dashboard/legacy` is not needed to settle it.

## Scope

- API: `GET /needs-you` and `GET /projects/{id}/needs-you` carry gates (no task; a `gate` object with the conflict, reason and proposed order with sprint titles). The workspace `needs_you` counts include them.
- Store: one grouped read, `list_pending_decision_gates`.
- Frontend: `NeedsYou` row with Accept / Reject over the existing `PATCH /gates/{id}`; new `api/gates.js`.
- Placement: Needs you, as the task proposed. The design README names four kinds; noted in STATUS.

## Files changed

- `foreman/store/overview.py`, `foreman/dashboard_overview.py`
- `frontend/src/api/{gates,needsYou}.js`, `frontend/src/pages/shared/NeedsYou.jsx`, `frontend/src/styles/lists.css`
- tests: `tests/test_dashboard_workspace_api.py`, `frontend/src/pages/project/ProjectPage.test.jsx`, fixture
- docs: `docs/STATUS.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`; rebuilt bundle in its own commit

## Migrations

- none

## Risks

- Clients that assume every needs-you item has a task id must handle null (the rebuilt frontend does).
- The gate's sprint link goes to `/dashboard/sprints/{id}`, which is still the "being rebuilt" page until the sprint-page slice lands.

## Tests

- `tests.test_dashboard_workspace_api` (listing, counts, settling removes it, constant query count); vitest `ProjectPage` accept and reject.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A pending sprint-order decision is visible and can be settled from the rebuilt dashboard; tested.

## Follow-ups

- The removal slice can drop the legacy gate UI.
