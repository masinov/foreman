# Sprint 35 — Dashboard CRUD Polish

- **Branch:** `main` (landed directly — three independent bug/feature slices)
- **Merged:** 2026-04-01
- **Status:** done

## Goal

Close the remaining dashboard CRUD and presentation gaps identified after
sprint-34: a board-view filter leak, missing delete surfaces, sprint title
editing, and sprint ordering / date tracking.

## Tasks completed

| # | Task | Deliverable |
|---|------|-------------|
| 1 | Board-view filter leak fix | `STATUS_FILTER_OPTIONS` and sort button now conditioned on `viewMode === "list"`; were previously always rendered and non-functional in board view |
| 2 | Delete task | `ForemanStore.delete_task()` (cascade events → runs → task); `DashboardService.delete_task()`; `DELETE /api/tasks/{id}`; `deleteTask()` in api.js; Delete task button in `TaskDetailDrawer` with `window.confirm` guard |
| 3 | Delete sprint | `ForemanStore.delete_sprint()` (cascade events → runs → tasks → sprint); `DashboardService.delete_sprint()`; `DELETE /api/sprints/{id}`; `deleteSprint()` in api.js; Delete sprint button on sprint cards (list view) and in sprint view header; navigates to project view when current sprint is deleted |
| 4 | Sprint title editing | Inline edit in sprint view header (same pattern as goal edit); `editingTitle`/`titleDraft` state; calls `PATCH /api/sprints/{id}` with `{title}`; `handleUpdateSprintTitle` in App |
| 5 | Sprint ordering | `order_index`, `started_at`, `completed_at` added to all sprint API responses; `order_index` now editable via `PATCH /api/sprints/{id}`; `handleReorderSprint` swaps adjacent order values via two parallel PATCH calls; ↑/↓ buttons in sprint card actions; sort fixed from `s.order` (always undefined) to `s.order_index`; default sort changed to ascending (first-to-do at top) |
| 6 | Date display | `formatDate` added to `format.js`; `started_at` and `completed_at` shown on sprint cards as "started MMM D" / "closed MMM D" second line; sprint view header shows same dates as stats |
| 7 | Tests | `DashboardDeleteTests` (10 tests); `DashboardSprintOrderTests` (8 tests) |

## Files changed

| File | Change |
|------|--------|
| `foreman/store.py` | `delete_task()`, `delete_sprint()` — cascade delete in correct FK order |
| `foreman/dashboard_service.py` | `delete_task()`, `delete_sprint()`; `order_index`/`started_at`/`completed_at` added to `list_project_sprints` and `get_sprint` responses; `order_index` added to `update_sprint_fields` allowed fields |
| `foreman/dashboard_backend.py` | `DELETE /api/tasks/{id}`, `DELETE /api/sprints/{id}` |
| `frontend/src/api.js` | `deleteTask()`, `deleteSprint()` |
| `frontend/src/format.js` | `formatDate` (locale date formatter) |
| `frontend/src/App.jsx` | `editingTitle`/`titleDraft` state; `handleUpdateSprintTitle`, `handleDeleteTask`, `handleDeleteSprint`, `handleReorderSprint`; sprint title inline edit UI; Delete sprint button in header; dates in header stats; `formatDate` import; `onDelete` on `TaskDetailDrawer`; `onDeleteSprint`, `onReorderSprint` on `SprintList` |
| `frontend/src/components.jsx` | `SprintList` — filter/sort buttons gated on `viewMode === "list"`; `onDeleteSprint`, `onReorderSprint` props; ↑/↓ buttons in sc-actions; `sc-body` to column flex with inner `.sc-body-main` row; dates as second line; sort uses `order_index`; `TaskDetailDrawer` — `onDelete` prop; Delete task button |
| `frontend/src/styles.css` | `.btn-delete-task`, `.btn-danger-sm`, `.sc-action-order`, `.sc-dates`, `.sc-body-main`; `.sc-body` changed to column flex; `.sprint-title-input`, `.sprint-title-edit` |
| `tests/test_dashboard.py` | `DashboardDeleteTests` (10 tests), `DashboardSprintOrderTests` (8 tests) |
| `foreman/dashboard_frontend_dist/` | Rebuilt |

## Test results

- 95 dashboard unit/integration tests: all pass
- 20 E2E tests: all pass

## Notes

- `delete_task` and `delete_sprint` both require strict cascade order (events →
  runs → tasks → sprint) because `PRAGMA foreign_keys = ON` is enforced in
  `ForemanStore`.
- `handleReorderSprint` fires two `updateSprint` calls in parallel; if both
  sprints have the same `order_index` (e.g. pre-existing DB with all zeros),
  the swap is a no-op visually — acceptable.
- `sc-order` badge (the `#N` prefix attempted earlier) was removed: the list
  sorted by `order_index` already communicates position; a badge only added
  visual noise and broke the 4-column grid.
- `.sc-body` is now a column flex; `.sc-body-main` is the inner horizontal row
  for title + goal, preserving overflow/truncation behaviour.

## Remaining Tier 3 items

- SSE transport hardening: stream loop polls SQLite directly inside FastAPI;
  final design requires an in-process pub/sub layer. Lowest urgency.
