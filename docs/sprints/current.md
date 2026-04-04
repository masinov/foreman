# Current Sprint

- Sprint: `sprint-40-meta-agent-panel`
- Status: done
- Branch: `feat/sprint-40-meta-agent-panel`
- Started: 2026-04-04
- Completed: 2026-04-04

## Goal

Replace the sprint-39 wrong planner implementation with the correct meta agent:
a persistent Claude Code subprocess session accessible from a right-side
slide-in panel on the project's sprint list view. The agent has full access to
the repo, git, and Foreman CLI. Session history persists and is restored when
the panel reopens.

## Tasks

### 1. Remove sprint-39 planner

- Status: done
- Deleted `foreman/planner.py` and `roles/sprint-planner.toml`
- Removed `/planner/*` endpoints from `dashboard_backend.py`
- Replaced planner API methods in `api.js`
- Removed `PlannerPanel` from `components.jsx`

### 2. foreman/meta_agent.py

- Status: done
- In-memory session registry per project (`_sessions` dict)
- Claude Code backend: `asyncio.create_subprocess_exec` with
  `claude --print --output-format stream-json [--resume session_id]`
- Rich Foreman context injected on first message (project, repo, sprints)
- `process_message()` async generator: NDJSON events
  (text_delta, tool_use, done, error)
- `get_history()` / `clear_session()`
- Graceful error when `claude` binary not in PATH

### 3. Backend endpoints

- Status: done
- `POST /api/projects/{id}/meta/message` — streaming NDJSON
- `GET /api/projects/{id}/meta/history` — stored turns
- `DELETE /api/projects/{id}/meta/session` — clear in-memory session

### 4. Frontend

- Status: done
- `api.js`: `metaMessage`, `metaHistory`, `clearMetaSession`
- `MetaAgentPanel`: right-side fixed slide-in; loads history on open; streaming
  text with cursor; tool-use chips; Enter to send, Shift+Enter newline;
  Clear/Close buttons
- `SprintList`: `metaOpen` state + "Meta agent" toggle in sprint-page-bar
- `SettingsPanel`: Meta Agent section with backend selector (Claude Code / Codex)
- CSS: `.meta-panel`, `.meta-toggle-btn`, `.meta-turn-*`, `.meta-tool-*`,
  `.meta-cursor`, `.meta-input-row`, `.meta-send-btn`

### 5. Tests

- Status: done
- Replaced `DashboardPlannerTests` (9 tests) with `DashboardMetaAgentTests`
  (7 tests): history empty/404, clear session/404, message 400/404,
  history-reflects-cleared-session
- `test_loads_shipped_roles` updated: removed sprint-planner from expected set
