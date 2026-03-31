# Current Sprint

- Sprint: `sprint-34-task-edit-enforcement`
- Status: done
- Goal: close the Tier 3 task-editing enforcement gap — emit `human.task_edited`
  events when in-progress or blocked tasks are edited from the dashboard
- Branch: `feat/sprint-34-task-edit-enforcement`
- Primary references:
  - `foreman/dashboard_service.py`
  - `frontend/src/format.js`
  - `tests/test_dashboard.py`

## Included tasks

1. `[done]` Task editing enforcement
   Deliverable: `update_task_fields()` tracks actually-changed fields; for
   `in_progress` and `blocked` tasks with at least one real change, emits a
   `human.task_edited` event with `changed_fields` payload. Synthetic run
   created if task has no run history. `todo`/`done`/`cancelled` edits remain
   silent. Frontend `getEventCategory` broadened to `human.*` prefix so all
   human events appear under the "Human" filter.

2. `[done]` 6 new tests in `DashboardTaskEditEventTests`

## Acceptance criteria

- PATCH in-progress task title → `human.task_edited` event with `title` in
  `changed_fields`
- PATCH blocked task criteria → `human.task_edited` event with
  `acceptance_criteria` in `changed_fields`
- PATCH todo task → no event emitted
- PATCH with no actual change → no event emitted
- 78 dashboard tests pass; 20 E2E tests pass
