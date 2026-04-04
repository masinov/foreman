# Current Sprint

- Sprint: `sprint-39-planner-chat`
- Status: done
- Branch: `feat/sprint-39-planner-chat`
- Started: 2026-04-04
- Completed: 2026-04-04

## Goal

Land the sprint planner chat MVP: an embedded chat panel in the sprint view
backed by a Claude Messages API session with eight Foreman management tools.
The agent can create, update, delete, and reorder sprints and tasks directly
through the existing dashboard service layer. Changes apply live.

## Tasks

### 1. Anthropic SDK

- Status: done
- `anthropic>=0.89` added to `pyproject.toml` dependencies and installed

### 2. Role definition

- Status: done
- `roles/sprint-planner.toml` with `backend = "anthropic_messages"`,
  restricted tool list, and planning-focused system prompt
- Role loader compatibility ensured (completion section, permission_mode)

### 3. Planner service — foreman/planner.py

- Status: done
- 8 tool definitions (JSON schema for Anthropic tool_use API):
  list/create/update/delete for sprints and tasks
- `_execute_tool` dispatcher calls DashboardService methods directly
- In-memory session history per project (`_sessions` dict)
- `process_message` async generator: streaming NDJSON events
  (text_delta, tool_use, tool_result, done, error)
- Graceful handling of missing API key or SDK

### 4. Backend endpoints

- Status: done
- `POST /api/projects/{id}/planner/message` — streaming NDJSON response
- `GET /api/projects/{id}/planner/history` — simplified turn list
- `DELETE /api/projects/{id}/planner/session` — clear in-memory session

### 5. Frontend

- Status: done
- `api.js`: `plannerMessage` (async generator over NDJSON stream),
  `plannerHistory`, `clearPlannerSession`
- `PlannerPanel` component: collapsible, docked at bottom of sprint view;
  streaming text with cursor animation; tool use chips (running/done);
  Enter to send, Shift+Enter for newline; Clear session button
- `SprintList` accepts `services` and `onSprintsChanged` props;
  renders PlannerPanel when services is provided
- App.jsx passes `services` and sprint refresh callback
- CSS: `.planner-panel`, `.planner-toggle`, `.planner-turn-*`,
  `.planner-tool-chip`, `.planner-cursor` with blink/pulse animations

### 6. Tests

- Status: done
- `DashboardPlannerTests` (9 tests): history empty/404, clear session/404,
  message 400/404, tool executor list_sprints, create_sprint, unknown tool
- `test_loads_shipped_roles` updated to include sprint-planner
