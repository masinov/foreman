# Current Sprint

- Sprint: `sprint-41-sprint-queue-and-advancement`
- Status: done
- Branch: `feat/sprint-41-sprint-queue-and-advancement`
- Started: 2026-04-04
- Completed: 2026-04-05

## Goal

Wire the sprint queue end-to-end: orchestrator auto-advances through planned
sprints according to the project's autonomy level, the UI reflects the serial
pipeline reality (Active / Next Up / Queue / Archive), and the Promote button
has a clear, unambiguous meaning (move to top of queue — not activate).

This sprint does two things that must land together: the engine wiring and the
UI. Landing one without the other leaves the product in a contradictory state.

## Context and rationale

The orchestrator loop currently stops dead when the active sprint's tasks are
exhausted. It does not advance to the next planned sprint. The `autonomy_level`
field on Project is stored and exposed in the UI but is never read by the
orchestrator. The `Start`/`Promote` button on sprint cards transitions a sprint
directly to `active`, which conflicts with the backend guard that rejects a
second active sprint while one is running. The kanban view treats all sprints as
equal-weight peers, which is wrong for a serial queue-driven workflow.

The spec already defines `activate_next_sprint` and sprint completion actions
(§6.3–6.4 of engine-design-v3.md). This sprint implements them.

## Constraints

- One active sprint at a time — this invariant must hold throughout.
- `autonomy_level` on Project (directed / supervised / autonomous) is the
  authoritative field for sprint advancement behavior. The orchestrator must
  read it directly, not infer it from `task_selection_mode` in settings.
- `task_selection_mode` in settings governs task selection within a sprint
  (directed = pick next todo task; autonomous = create placeholder). These are
  orthogonal: `autonomy_level` governs sprint-to-sprint progression.
- The `Start`/`Promote-to-active` button is removed. Queue order is the intent
  signal. Run auto-activates the first planned sprint if none is active.
- The kanban view is removed. The new 4-zone layout replaces it entirely.

## Affected areas

- `foreman/orchestrator.py` — sprint completion and advancement loop
- `foreman/store.py` — `get_next_planned_sprint`
- `foreman/dashboard_service.py` — `start_agent` auto-activation
- `frontend/src/components.jsx` — new project view layout, Promote button
- `frontend/src/styles.css` — new layout CSS
- `tests/test_orchestrator.py` (or equivalent) — sprint advancement tests
- `tests/test_dashboard.py` — start_agent auto-activation test

## Implementation plan

---

### Task 1 — Store: `get_next_planned_sprint`

Add to `ForemanStore`:

```python
def get_next_planned_sprint(self, project_id: str) -> Sprint | None:
    """Return the first planned sprint by order_index, or None."""
```

Query: `WHERE project_id = ? AND status = 'planned' ORDER BY order_index ASC,
created_at ASC, id ASC LIMIT 1`.

---

### Task 2 — Orchestrator: sprint completion and advancement

In `run_project`, after `select_next_task` returns `None`:

```
if sprint is fully resolved (all tasks done or cancelled):
    mark sprint completed (status = "completed", completed_at = now)
    emit engine.sprint_completed
    next_sprint = store.get_next_planned_sprint(project.id)
    if next_sprint is None:
        stop — no more sprints
    elif project.autonomy_level == "autonomous":
        activate next_sprint (status = "active", started_at = now)
        emit engine.sprint_started
        continue loop
    else:  # "supervised" or "directed"
        emit engine.sprint_ready (next_sprint_id, next_sprint_title)
        stop — human will press Run again
else:
    stop — blocked tasks remain
```

"Fully resolved" means every task in the sprint is `done` or `cancelled`. Any
`blocked`, `todo`, or `in_progress` task prevents completion.

The distinction between `supervised` and `directed` at the engine level is only
in the event emitted and the UI treatment — both stop and wait for human. The
`engine.sprint_ready` event is emitted only in supervised mode as a signal to
the dashboard to show a prominent "next up" confirmation prompt.

---

### Task 3 — Dashboard service: `start_agent` auto-activation

In `start_agent`, before spawning the subprocess:

```python
if store.get_active_sprint(project_id) is None:
    next_sprint = store.get_next_planned_sprint(project_id)
    if next_sprint is not None:
        next_sprint.status = "active"
        next_sprint.started_at = now
        store.save_sprint(next_sprint)
        emit engine.sprint_started event
```

This replaces the `Start`/`Promote-to-active` button entirely. Pressing Run
when no sprint is active automatically starts the first one in queue order.

If no planned sprint exists either, `start_agent` returns a validation error:
"No active or planned sprint. Add a sprint to the queue before running."

---

### Task 4 — Frontend: new project view layout

Replace the current list/board toggle with a single fixed layout:

**Zone 1 — Active** (top, prominent)

If a sprint is active:
- Sprint title and goal
- Task progress: todo / in_progress / blocked / done counts + progress bar
- Agent status indicator (running / idle / blocked)
- Run/Stop button
- Click anywhere on the zone → opens sprint view (existing behavior)

If nothing is active and `autonomy_level === "supervised"`:
- Show "Next up: [Sprint Title]" with a Run button and a note that the system
  will start this sprint when you press Run.

If nothing is active otherwise:
- Idle state: "No active sprint. Press Run to start the queue."

**Zone 2 — Next Up**

The first planned sprint by order_index, rendered as a distinct card above the
queue. Shows title, goal, task count. No Promote button needed here — it is
already the next sprint.

If no planned sprints exist: zone is hidden.

**Zone 3 — Queue**

Remaining planned sprints (position 2 onwards). Compact cards: title, goal,
task count. ↑/↓ reorder arrows. Promote button on each card (moves to position
0 in planned queue, which bumps it into the Next Up zone). New Sprint button at
the bottom.

**Zone 4 — Archive**

Single collapsed row: "N completed sprints ▼". Expands to show a compact list
of completed and cancelled sprints with their dates. Collapsed by default.

**Remove:**
- List/Board view toggle (ViewMode state, viewToggle element, all kanban code)
- `Start` button on sprint cards (the one that transitions to `active`)
- `STATUS_FILTER_OPTIONS` toolbar (no longer needed — zones replace filtering)
- `newestFirst` sort toggle (archive is always newest-first by completed_at)

**Promote button behavior:**
Calls `onReorderSprint` to move the sprint to `order_index = 0` among planned
sprints. Does not transition status. Does not require a running agent.

---

### Task 5 — Tests

**Orchestrator advancement tests** (new test class `SprintAdvancementTests`):
- `directed` mode: all tasks done → sprint completed, no next sprint activated,
  stop_reason reflects completion
- `supervised` mode: same stop behavior, `engine.sprint_ready` event emitted
- `autonomous` mode: sprint completed, next planned sprint activated, loop
  continues into next sprint's tasks
- `autonomous` mode, no next sprint: loop stops after completing last sprint
- Blocked tasks prevent sprint completion in all modes
- Sprint with mixed done/cancelled tasks is treated as fully resolved

**Dashboard service test:**
- `start_agent` with no active sprint and a planned sprint → planned sprint
  activated before subprocess spawned
- `start_agent` with no active and no planned sprint → validation error

---

## Risks

- The orchestrator sprint advancement runs inside the `foreman run` subprocess.
  If the subprocess is killed mid-sprint-transition (after completing the sprint
  but before activating the next), the completed sprint will be in `completed`
  state and the next sprint will still be `planned`. The next Run call will
  re-activate it correctly — this is safe.
- Removing the kanban view is a visible regression if anything depends on
  `viewMode` state externally. Check App.jsx for any `viewMode` references
  before removing.
- The `engine.sprint_ready` event type is new. Existing event category
  handling in the frontend (`getEventCategory`) needs to cover it or it will
  render as an unknown event in the activity stream.

## Validation

- `./venv/bin/python -m pytest tests/ -x -q`
- Manual: create project with 3 planned sprints, set `autonomy_level` to each
  of the three values, press Run, verify advancement behavior matches spec
- Manual: verify Promote moves a sprint into Next Up zone without activating it
- Manual: verify Run with no active sprint auto-activates first planned sprint
- Manual: verify archive zone collapses/expands and shows correct count
