# Sprint 34 — Task Editing Enforcement

- **Branch:** `feat/sprint-34-task-edit-enforcement`
- **Merged:** 2026-04-01
- **Status:** done

## Goal

Close the Tier 3 task-editing enforcement gap: edits to `in_progress` or
`blocked` tasks now emit a `human.task_edited` event so the activity log
reflects the change and the agent can account for it on its next run.

## What changed

**Rule:** `update_task_fields()` tracks which fields actually changed (not just
which fields were submitted). For `in_progress` and `blocked` tasks with at
least one real change, it emits a `human.task_edited` event with a
`changed_fields` payload. For `todo`, `done`, and `cancelled` tasks the update
remains silent.

**Synthetic run:** If the task has no run history (edge case in tests, possible
in practice for manually-created tasks), a minimal `dashboard/edit` synthetic
run is created to satisfy the `events.run_id` FK constraint — same pattern the
orchestrator uses for pruning events.

**Frontend:** `getEventCategory` broadened from `human.message` exact match to
`startsWith("human.")` so all `human.*` events (stop, message, task_edited)
are grouped under the "Human" activity filter. `formatEventSummary` handles
`human.task_edited` by listing the changed field names.

## Files changed

| File | Change |
|------|--------|
| `foreman/dashboard_service.py` | `update_task_fields` — change tracking, conditional event emission, synthetic run creation; added `Run` to imports |
| `frontend/src/format.js` | `getEventCategory`: `human.*` prefix match; `formatEventSummary`: `human.task_edited` summary |
| `foreman/dashboard_frontend_dist/` | Rebuilt |
| `tests/test_dashboard.py` | `DashboardTaskEditEventTests` (6 tests) |

## Test results

- 78 dashboard tests: all pass
- 20 E2E tests: all pass

## Notes

- The `"none"` run_id pattern in `stop_agent` and `create_human_message` has
  the same latent FK risk; not fixed here to keep the scope narrow.
- No changes to the API surface — `PATCH /api/tasks/{id}` response is unchanged.
- Dependency ordering was discovered to already be implemented in
  `select_next_task` (directed mode) with a passing test. Tier 3 memory
  updated accordingly.
