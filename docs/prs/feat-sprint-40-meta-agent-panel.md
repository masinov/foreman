# PR: feat/sprint-40-meta-agent-panel

## Summary

- Replaced the wrong sprint-39 planner implementation with the correct meta
  agent: a persistent Claude Code subprocess session per project, accessible
  from a right-side collapsible sidebar panel on the project sprint list view
- Panel matches the Activity panel pattern from the task screen — grid-based
  collapsible layout, spanning full height from header to bottom
- Fixed a silent subprocess failure: `--output-format stream-json` requires
  `--verbose`; without it Claude Code exits with no output
- Scoped sprint list filters to the executed-sprints panel only; planned
  sprints are always visible; removed the nonsensical "Planned" filter button
- Cleaned up dead `"done"` sprint status references (task status leaked into
  sprint components)

## Scope

- `foreman/meta_agent.py` — new module; session registry, subprocess spawn,
  NDJSON streaming
- `foreman/dashboard_backend.py` — three new meta endpoints; planner endpoints
  removed
- `frontend/src/api.js` — `metaMessage`, `metaHistory`, `clearMetaSession`;
  planner methods removed
- `frontend/src/components.jsx` — `MetaAgentPanel`, `SprintList` collapsible
  grid layout, filter scoping, status cleanup
- `frontend/src/styles.css` — `.project-view-inner`, `.project-left`,
  `.agent-panel`, `.agent-tab`, `.meta-panel` and related rules
- `tests/test_dashboard.py` — `DashboardMetaAgentTests` (7 tests)
- `roles/sprint-planner.toml` — deleted
- `foreman/planner.py` — deleted

## Files changed

- `foreman/meta_agent.py` (new)
- `foreman/dashboard_backend.py`
- `frontend/src/api.js`
- `frontend/src/components.jsx`
- `frontend/src/styles.css`
- `tests/test_dashboard.py`
- `roles/sprint-planner.toml` (deleted)
- `foreman/planner.py` (deleted)

## Migrations

None.

## Risks

- Meta agent sessions are in-memory only; server restart clears all history.
  Acceptable for now — persistent history is a future slice.
- `--permission-mode bypassPermissions` gives the subprocess full tool access.
  Appropriate since the panel is operator-controlled, but worth revisiting if
  the product adds multi-user or untrusted-input scenarios.

## Tests

- 7 new `DashboardMetaAgentTests` in `tests/test_dashboard.py`; all passing
- `test_loads_shipped_roles` updated to reflect planner removal

## Acceptance criteria satisfied

- Right-side collapsible sidebar panel on project sprint list view
- Panel spans full height from header to bottom (matching Activity panel)
- Persistent Claude Code subprocess session per project
- Conversation history stored and restored when panel reopens
- Streaming text with tool-use chips
- Clear session button
- Sprint list filters scope to executed sprints only; planned always visible

## Follow-ups

- Persist meta agent history to SQLite (survive server restarts)
- Kanban board drag-and-drop reordering for planned column (backlog)
- E2E test coverage for meta agent panel
