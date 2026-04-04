# ADR-0007: Sprint Planner Chat Session

- Status: accepted
- Date: 2026-04-04

## Context

Creating and managing sprints currently requires leaving the dashboard entirely.
The workflow is:

1. Open a terminal in the project directory (or clone the project into Claude
   web or a Codex session).
2. Converse with an agent to draft sprint goals, tasks, and ordering.
3. Manually transcribe the result back into Foreman — either by running CLI
   commands or by typing into the dashboard form fields one by one.

This is the correct mental model for sprint co-authoring (a conversation with
an AI that has Foreman tool access), but the execution is painful. The
transcript-and-retype step is lossy and slow, and there is no durable link
between the conversation and the resulting sprint state.

The right surface is an embedded agent chat panel in the sprint view, backed by
a real Claude Code or Codex session that has Foreman sprint management as its
tool layer. The agent in that session can create sprints, add tasks, reorder the
queue, and update sprint goals directly through the Foreman API — the same API
the dashboard frontend uses. Changes appear live in the sprint list as the
conversation happens.

This is not a general-purpose code execution surface. The session is scoped
to sprint and task management for the current project. Code execution is not
permitted in planner sessions.

## Decision

### 1. The planner session is a first-class runner mode

Foreman's runner infrastructure already supports Claude Code and Codex backends
(ADR-0001). A planner session is a third entry point into the same
infrastructure with a distinct role, a restricted tool set, and a chat-mode
interaction model rather than an autonomous execution model.

The planner session is not a general REPL. It is a purpose-scoped agent with
access to Foreman management tools only.

### 2. Role definition: sprint-planner

A new role `roles/sprint-planner.toml` defines the planner session contract:

```toml
id = "sprint-planner"
backend = "claude"          # or "codex"; selectable per project or session
session_persistence = true  # conversation continues across panel open/close
permission_mode = "default"
disallowed_tools = [
  "Bash",
  "computer_use",
]

[tools]
# Foreman management tools available to this role
allowed = [
  "foreman:list_sprints",
  "foreman:create_sprint",
  "foreman:update_sprint",
  "foreman:delete_sprint",
  "foreman:reorder_sprints",
  "foreman:list_tasks",
  "foreman:create_task",
  "foreman:update_task",
  "foreman:delete_task",
]

[system_prompt]
# Injected at session start; template variables filled by the backend
template = """
You are a sprint planning collaborator for the Foreman project management system.
Your role is to help the user design, refine, and organize sprints and tasks for
the project "{{ project.name }}" (ID: {{ project.id }}).

Current sprint queue:
{{ sprint_summary }}

You have access to Foreman management tools. Use them to apply changes directly —
do not describe changes without applying them unless the user asks you to preview
first.

You do not have access to code execution tools. Do not attempt to run shell
commands, read source files, or interact with the file system.
"""
```

### 3. Foreman management tools

The planner session's tools are thin wrappers over existing dashboard API
endpoints. They are not a separate implementation — they call the same service
layer that the REST API calls.

Each tool maps to one API operation:

| Tool name | API call |
|---|---|
| `foreman:list_sprints` | `GET /api/projects/{id}/sprints` |
| `foreman:create_sprint` | `POST /api/projects/{id}/sprints` |
| `foreman:update_sprint` | `PATCH /api/sprints/{id}` |
| `foreman:delete_sprint` | `DELETE /api/sprints/{id}` |
| `foreman:reorder_sprints` | `PATCH /api/sprints/{id}` × N (order_index updates) |
| `foreman:list_tasks` | `GET /api/sprints/{id}/tasks` |
| `foreman:create_task` | `POST /api/sprints/{id}/tasks` |
| `foreman:update_task` | `PATCH /api/tasks/{id}` |
| `foreman:delete_task` | `DELETE /api/tasks/{id}` |

The planner session talks to Foreman's own API, not directly to SQLite. All
persistence goes through the same validation and event-emission path as
human-initiated actions.

### 4. Backend and transport

**Backend process**: A planner session spawns a Claude Code or Codex subprocess
using the `sprint-planner` role. The backend choice (Claude vs Codex) is set
at the project level, with a per-session override available.

**Chat endpoint**: The dashboard backend exposes a streaming endpoint:

```
POST /api/projects/{project_id}/planner/start
     → { session_id, ... }

POST /api/projects/{project_id}/planner/message
     body: { session_id, message }
     → streaming NDJSON of agent response deltas and tool use events

GET  /api/projects/{project_id}/planner/history
     → recent conversation turns for the current session
```

The streaming transport follows the same incremental event model as the runner
event stream. Tool use events are emitted as they happen so the frontend can
show what the agent is doing (e.g. "Creating sprint: Authentication refactor…")
before the full response arrives.

**Session persistence**: `session_persistence = true` in the role means the
conversation continues across panel close and reopen within the same project.
The session ID is stored against the project in the backend's running-process
registry and reused on the next open.

### 5. Frontend panel

A collapsible chat panel docks at the bottom or right side of the sprint view.
It is not a modal — the sprint list remains visible and updates live as the
agent applies changes.

Panel anatomy:

- **Header**: "Sprint planner" label, backend indicator (Claude / Codex),
  collapse button, clear session button
- **Conversation area**: scrollable list of human and agent turns; tool use
  events shown inline as status lines ("Created sprint: Auth refactor",
  "Added 3 tasks to sprint")
- **Input**: textarea + send button; supports multi-line input for pasting
  in rough task lists or spec excerpts

The panel is a frontend-only surface. It does not introduce a new page route.

### 6. What the planner session is not

- It is not a code execution environment. The `sprint-planner` role explicitly
  disallows Bash and file system tools.
- It is not a general assistant. The system prompt scopes it to sprint and task
  management for the current project.
- It is not a replacement for the existing sprint form UI. The form remains
  for users who prefer direct manipulation.
- It is not a replacement for autonomous sprint execution. The planner session
  is a human-in-the-loop collaborative tool; execution remains a separate
  runner invocation.

### 7. Autonomy level interaction

The planner session is always human-in-the-loop regardless of the project's
`autonomy_level` setting (ADR-0006). The human initiates each message; the
agent responds and applies changes. The planner session does not trigger sprint
execution and does not interact with the agent runner that executes sprint tasks.

### 8. Audit trail

All changes made through the planner session flow through the standard API and
are indistinguishable in the event log from human-initiated dashboard actions.
If attributing planner-originated changes becomes important in future, a
`source: "planner"` field can be added to relevant event types. That is not
required now.

## Consequences

- The `sprint-planner` role TOML must be committed and loaded by the role
  system before the planner session can be used.
- The Foreman management tools (the thin API wrappers) must be implemented as
  a callable tool set the runner infrastructure can inject into a planner
  session, separate from the standard agent tool set.
- The backend must expose the three planner endpoints before the frontend panel
  can be wired up.
- Session persistence for the planner means the backend must not eagerly clean
  up planner processes on panel close; it must reuse or resume them.
- The frontend sprint view gains a new docked panel; this is a visible layout
  change that should be validated against the mockup hierarchy.
- Future changes to the dashboard API that add or remove sprint/task operations
  must also evaluate whether the planner tool set should be updated.

## References

- `docs/specs/engine-design-v3.md`
- `docs/adr/ADR-0001-runner-session-backend-contract.md`
- `docs/adr/ADR-0006-sprint-autonomy-levels.md`
- `foreman/dashboard_service.py`
- `foreman/dashboard_backend.py`
- `foreman/runner/`
- `roles/` (to be created)
- `frontend/src/components.jsx` (SprintList)
