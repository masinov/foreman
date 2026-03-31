# Sprint 32 — Tier 1 Editing Polish

- **Branch:** `feat/sprint-32-tier1-editing`
- **Merged:** 2026-03-31
- **Status:** done

## Goal

Implement the three Tier 1 UX gaps identified after sprint-31:
- Task field editing directly in the drawer (title, type, criteria)
- Sprint goal inline editing in the sprint view header
- Activity panel auto-scroll to bottom when new SSE events arrive

## Tasks completed

| # | Task | Deliverable |
|---|------|-------------|
| 1 | Task field editing UI | Edit mode in `TaskDetailDrawer`; `update_task_fields` extended |
| 2 | Sprint goal inline editing | `update_sprint_fields`; `PATCH /api/sprints/{id}` dual routing |
| 3 | Activity auto-scroll | `containerRef`/`onScroll` on `EventList`; `useLayoutEffect` in App |
| 4 | Tests | 11 tests in `DashboardTaskEditingTests` |

## Files changed

- `foreman/dashboard_service.py` — `update_task_fields` extended to include
  `title`, `task_type`, `acceptance_criteria`; new `update_sprint_fields`
  method; added empty-updates guard
- `foreman/dashboard_backend.py` — `PATCH /api/sprints/{id}` routes to
  `update_sprint_fields` when `status` key absent, else `transition_sprint`
- `frontend/src/api.js` — added `updateSprint(sprintId, updates)`
- `frontend/src/App.jsx` — added `handleSaveTask`, `handleUpdateSprintGoal`;
  inline goal edit state (`editingGoal`, `goalDraft`); activity scroll tracking
  (`activityListRef`, `atActivityBottomRef`, `useLayoutEffect`); passed
  `onSave` to `TaskDetailDrawer`; sprint header goal edit UI
- `frontend/src/components.jsx` — `TaskDetailDrawer` gains `onSave`, `editing`
  state, title input, type chip selector, criteria textarea, Save/Cancel;
  `EventList` gains `containerRef` and `onScroll` props
- `frontend/src/styles.css` — editing UI styles for drawer and sprint header
- `tests/test_dashboard.py` — `DashboardTaskEditingTests` (11 tests)
- `foreman/dashboard_frontend_dist/` — rebuilt

## Test results

- 63 dashboard unit/integration tests: all pass
- 20 E2E tests: all pass

## Follow-up (Tier 2 / Tier 3)

See memory: `project_backlog_tiers.md` for remaining gaps.
