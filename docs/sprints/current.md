# Current Sprint

- Sprint: `sprint-40-meta-agent-panel`
- Status: done
- Branch: `feat/sprint-40-meta-agent-panel`
- Started: 2026-04-04
- Completed: 2026-04-05

## Goal

Replace the sprint-39 wrong planner implementation with the correct meta agent:
a persistent Claude Code subprocess session accessible from a right-side
collapsible sidebar panel on the project's sprint list view, matching the
Activity panel pattern in the task screen. The agent has full access to the
repo, git, and Foreman CLI. Session history persists and is restored when the
panel reopens.

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
  `claude --print --verbose --output-format stream-json [--resume session_id]`
- `--verbose` is required; without it Claude Code silently exits with no output
- `--permission-mode bypassPermissions` used for non-interactive subprocess
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
- `MetaAgentPanel`: right-side collapsible sidebar (grid-based, matching
  Activity panel pattern); loads history on open; streaming text with cursor;
  tool-use chips; Enter to send, Shift+Enter newline; Clear/Collapse buttons;
  panel title "Agent"
- `SprintList`: collapsible grid layout — `project-view-inner` is the CSS grid
  with columns `1fr` / `1fr 360px` / `1fr 32px`; `project-left` holds header
  and scrollable content; `agent-panel` and `agent-tab` are peer grid columns
  spanning full height from header to bottom
- `SettingsPanel`: Meta Agent section with backend selector (Claude Code / Codex)
- CSS: `.project-view-inner`, `.project-left`, `.agent-panel`, `.agent-tab`,
  `.meta-panel`, `.meta-turn-*`, `.meta-tool-*`, `.meta-cursor`,
  `.meta-input-row`, `.meta-send-btn`

### 5. Filter and status cleanup

- Status: done
- Sprint list filters now scope only to the executed-sprints box; planned
  sprints are always visible in their own section regardless of active filter
- Removed "Planned" filter button (not applicable to the executed panel)
- Filter label `"done"` corrected to `"completed"` to match `SprintStatus`
  model (`"done"` is a task status, not a sprint status)
- Removed dead `sprint.status === "done"` branches from card status class and
  board column filter
- `STATUS_RANK` map cleaned up: removed `done` key

### 6. Tests

- Status: done
- Replaced `DashboardPlannerTests` (9 tests) with `DashboardMetaAgentTests`
  (7 tests): history empty/404, clear session/404, message 400/404,
  history-reflects-cleared-session
- `test_loads_shipped_roles` updated: removed sprint-planner from expected set
