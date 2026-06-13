# PR Summary: fix/frontend-ux-correctness

## Summary

Tier-1 of the frontend UX review (`docs/reviews/frontend-ux-review.md`): fixes
the outright-wrong behaviours plus a cheap label/consistency pass. No backend
changes.

## Scope

- **Invalid task type** — the New Task chips offered `bug` (rejected by the
  backend with a 400) and omitted `fix`/`docs`/`spike`. `TASK_TYPE_CHIPS` and
  `getTaskTypeClass` now match the backend `TASK_TYPES`; added `tag-fix` /
  `tag-docs` / `tag-spike` styles.
- **Dead activity filters** — `File changes` and `Review` matched event types
  the engine never emits. `getEventCategory` was rewritten so every category
  (Agent / Workflow / Decisions / Human) is populated; the filter `<select>`
  and `EVENT_FILTERS` updated; `formatEventSummary` now renders
  `engine.attention_needed`, `engine.completion_evidence`,
  `workflow.model_selected`, `engine.completion_guard`, and the cost/time gate
  events.
- **Status vs agent_running contradiction** — new `deriveEngineState(project)`
  helper makes "Running" mean a live agent everywhere (landing card with a
  pulse dot, topbar engine status, breadcrumb project dropdown), so it no longer
  disagrees with the Run/Stop control. The breadcrumb sprint dropdown stops
  miscolouring `cancelled`.
- **Labels / consistency** — "{n} awaiting approval" → "{n} blocked"; sprint
  modal task "Context" → "Description"; evidence/supervision colours moved from
  hardcoded hex to the theme tokens (`--green/--red/--amber/--text-tertiary`).

## Files changed

- `frontend/src/format.js` (task-type map, event categories, summaries,
  `deriveEngineState`), `frontend/src/components.jsx`, `frontend/src/App.jsx`,
  `frontend/src/styles.css`; rebuilt `foreman/dashboard_frontend_dist/`.
- `frontend/src/format.test.js` (new, 6 tests); `CHANGELOG.md`.

## Tests

- `npm --prefix frontend test` → 10 passed (4 App + 6 new format unit tests).
- `npm --prefix frontend run build` → dist rebuilt.

## Acceptance criteria

- Creating a task can only pick a backend-valid type; all six types render with
  a distinct colour.
- No activity filter is dead; roadmap events read meaningfully in the feed.
- "Running" reflects a live agent consistently across landing, topbar, and
  breadcrumb.

## Tier 2 (same branch)

- **Approve/Deny scoped to real human gates.** New backend `awaiting_human_gate`
  flag on `get_task` and `list_sprint_tasks` (a task is at a gate when it's
  `blocked` and its `workflow_current_step` is a `_builtin:human_gate` step).
  `TaskCard`/`TaskDetailDrawer` show Approve/Deny only when the flag is set;
  other blocks get an explanatory note. (`dashboard_service.py`
  `_human_gate_step_ids`/`_at_human_gate`; +1 backend test.)
- **Cancelled lane.** The board renders a "Cancelled" column when the sprint has
  cancelled tasks.
- **Edit affordances.** Visible ✎ buttons on the sprint title and goal.
- **Planned-card cue.** Planned sprint cards show an expand chevron and
  "Click to expand" title so they're distinguishable from navigate-on-click
  cards.

## Follow-ups (remaining UX review items)

- Unify the two task-creation forms (inline queue editor vs modal).
- Roles inspection/editing surface; meta-history pagination + origin badges.
- Status-casing and empty-state-copy normalization.
