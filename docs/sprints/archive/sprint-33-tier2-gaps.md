# Sprint 33 — Tier 2 Feature Gaps

- **Branch:** `feat/sprint-33-tier2-gaps`
- **Merged:** 2026-04-01
- **Status:** done

## Goal

Close the three Tier 2 product gaps identified after sprint-32:
- Workflow step visibility on task card and drawer
- Project creation from dashboard (register project record without CLI)
- `foreman run` integration in dashboard (start agent via Run button)

## Tasks completed

| # | Task | Deliverable |
|---|------|-------------|
| 1 | Workflow step visibility | `workflow_current_step` added to `list_sprint_tasks` response; shown as `card-step` badge on in-progress cards and in drawer Details section |
| 2 | Project creation | `POST /api/projects` + `create_project()` service + `NewProjectModal` in dashboard overview; navigates to new project after creation |
| 3 | `foreman run` from dashboard | `POST /api/projects/{id}/agent/start` + `start_agent()` spawns `foreman run` subprocess; cleanup thread removes proc from tracking; sprint header shows Run ▶ or Stop ■ based on project status |
| 4 | Tests | 9 tests in `DashboardTier2Tests` |

## Files changed

- `foreman/dashboard_service.py` — added `create_project`, `start_agent`, `_running_procs`; added `workflow_current_step` to `list_sprint_tasks`; new imports: `subprocess`, `sys`, `threading`, `Path`, `Project`, `generate_project_id`
- `foreman/dashboard_backend.py` — `POST /api/projects`, `POST /api/projects/{id}/agent/start`; removed unused `generate_project_id` import
- `frontend/src/api.js` — `startAgent`, `createProject`
- `frontend/src/App.jsx` — `handleStartAgent`, `handleCreateProject`, `newProjectOpen` state; Run/Stop toggle in sprint header; `NewProjectModal` in JSX
- `frontend/src/components.jsx` — `workflow_current_step` badge on `TaskCard`; step field in `TaskDetailDrawer`; `ProjectOverview` gains header with New project button; `NewProjectModal` component
- `frontend/src/styles.css` — `.card-step`, `.detail-step`, `.dashboard-overview-header`, `.form-hint`
- `tests/test_dashboard.py` — `DashboardTier2Tests` (9 tests)
- `foreman/dashboard_frontend_dist/` — rebuilt

## Test results

- 72 dashboard tests: all pass
- 20 E2E tests: all pass

## Notes

- `start_agent` uses `Path(sys.executable).parent / "foreman"` to find the CLI in the same venv
- Project creation is "register" semantics only — no file scaffolding; the modal has a hint pointing to `foreman init`
- Duplicate-ID guard in `create_project` appends numeric suffix if slug collides
- `start_agent` prevents double-starts by checking `proc.poll()` on the stored process

## Follow-ups (Tier 3)

- Dependency ordering in orchestrator
- Task editing enforcement for active/blocked tasks
- SSE transport hardening
