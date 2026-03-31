# Current Sprint

- Sprint: `sprint-33-tier2-gaps`
- Status: done
- Goal: close the three Tier 2 product gaps — workflow step visibility, project
  creation from dashboard, and `foreman run` integration via dashboard Run button
- Branch: `feat/sprint-33-tier2-gaps`
- Primary references:
  - `foreman/dashboard_service.py`
  - `foreman/dashboard_backend.py`
  - `frontend/src/App.jsx`
  - `frontend/src/components.jsx`
  - `frontend/src/api.js`
  - `frontend/src/styles.css`
  - `tests/test_dashboard.py`

## Included tasks

1. `[done]` Workflow step visibility
   Deliverable: `workflow_current_step` added to `list_sprint_tasks()` response.
   `TaskCard` shows a `card-step` badge (accent colour) for in-progress tasks.
   `TaskDetailDrawer` Details section shows current step field.

2. `[done]` Project creation from dashboard
   Deliverable: `POST /api/projects` endpoint + `create_project()` service method.
   `NewProjectModal` in dashboard overview with name, repo_path, workflow selector,
   and a hint that `foreman init` handles file scaffolding. Navigates to the new
   project after creation. Duplicate-slug guard appends numeric suffix.

3. `[done]` `foreman run` dashboard integration
   Deliverable: `POST /api/projects/{id}/agent/start` endpoint + `start_agent()`
   service method. Spawns `foreman run` subprocess using venv-local `foreman` CLI.
   Background thread cleans up proc tracking when process exits. Prevents
   double-starts. Sprint header shows ▶ Run button when project is idle and
   ■ Stop agent when running.

4. `[done]` 9 new tests in `DashboardTier2Tests`

## Acceptance criteria

- `GET /api/sprints/{id}/tasks` returns `workflow_current_step` on each task
- `POST /api/projects` with name+repo_path creates a project record; empty name/path → 400
- `POST /api/projects/{id}/agent/start` returns `{started: true}` for known project; 404 for unknown
- 72 non-E2E tests pass; 20 E2E tests pass
