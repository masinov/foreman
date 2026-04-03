# ADR-0006: Sprint Autonomy Levels And Agent Decision Gates

- Status: accepted
- Date: 2026-04-04

## Context

Foreman is designed to support a wide spectrum of human involvement in sprint
execution — from fully manual control to fully autonomous agent-driven delivery.
The current implementation does not model this spectrum. Sprint lifecycle
affordances (activating a sprint, advancing to the next sprint, reordering the
queue) are accessible to both human and agent with no separation of intent,
permission, or conflict resolution.

Specifically:

- The "Start" button on a sprint card transitions any planned sprint to active,
  bypassing the queue order without indication or confirmation.
- The agent runner has no defined contract for how to treat the human-set queue
  order: whether to follow it strictly, defer to it as a hint, or ignore it.
- When the agent detects a dependency conflict or ordering contradiction, there
  is no channel to surface that conflict and wait for a human decision.
- There is no project-level setting that governs how much autonomy the agent has
  over sprint lifecycle decisions.

Without this model, the human and agent planes are muddled. Future orchestrator
work that needs to make sequencing decisions will have no contract to follow,
and the UI will have no basis for showing or hiding affordances appropriately.

## Decision

### 1. Autonomy level is a project-level property

`Project` gains an `autonomy_level` field with three named values:

- `directed`
- `supervised`
- `autonomous`

The field defaults to `supervised`. It is persisted in SQLite and exposed
through the project API. The dashboard UI exposes it as a project setting.

### 2. The three autonomy levels

**Directed**

The human controls all sprint lifecycle transitions explicitly.

- The agent executes only the currently active sprint and stops when it
  completes. It does not auto-advance.
- The agent never modifies `order_index` or sprint status.
- The "Start" button on a sprint card is the primary activation mechanism.
- The `▶ Run` button triggers the agent on the currently active sprint only.
- There is no contradiction detection — the human is driving sequencing.

**Supervised** *(default)*

The agent follows the human-set queue order as a strict contract, not a hint.

- When a sprint completes, the agent automatically activates the next sprint in
  `order_index` order and continues without requiring a manual trigger.
- The agent never reorders the queue on its own. `order_index` values set by
  the human are treated as authoritative.
- If the agent detects a sequencing contradiction it cannot resolve within the
  current order (e.g. a dependency that requires a later sprint to have
  completed first), it stops and raises a **decision gate**. It does not
  proceed, reorder, or skip.
- The decision gate surfaces the conflict, the agent's analysis, and its
  suggested alternative order. The human accepts, rejects, or adjusts, then
  the agent resumes.
- The "Start" button remains available as an explicit override but is labeled
  to make the queue-bypass intent clear.

**Autonomous**

The agent manages sprint sequencing entirely according to its own reasoning.

- The human-set `order_index` values are visible to the agent as a starting
  preference but are not a contract.
- The agent may activate sprints, reorder the queue, and advance through
  sprints without consulting the human.
- The agent still respects stop signals from the human at all times. A stop
  is always honored regardless of autonomy level.
- The "Start" per-sprint button is hidden in this mode — it has no meaningful
  role when the agent owns activation.

### 3. Decision gates (Supervised mode)

A decision gate is a persisted blocking state raised by the agent when it
detects a contradiction it cannot resolve within the current queue contract.

A decision gate record includes:

- `project_id`
- `sprint_id` — the sprint at which the contradiction was detected
- `raised_at` timestamp
- `conflict_description` — plain-language description of what the agent found
- `suggested_order` — the agent's proposed `order_index` sequence as a JSON
  array of sprint IDs
- `suggested_reason` — plain-language rationale for the suggestion
- `status`: `pending | accepted | rejected | dismissed`
- `resolved_at` timestamp (nullable)
- `resolved_by`: `human | timeout`

Decision gates are persisted in a `decision_gates` table in SQLite. They
survive process restarts and page refreshes.

The dashboard surfaces an active decision gate as a persistent banner in the
sprint view and as a badge on the project entry in the sidebar. The banner
remains visible until the gate is resolved. The agent's subprocess is expected
to poll for gate resolution before continuing.

The human resolves a gate by:
- **Accepting** the suggestion: `order_index` values are updated to match
  `suggested_order` and the agent is signaled to resume.
- **Rejecting** the suggestion: the current `order_index` values are preserved.
  The agent resumes from its current position. The human accepts responsibility
  for the contradiction.
- **Dismissing**: equivalent to reject, but marks the gate as acknowledged
  so it does not re-raise immediately for the same contradiction.

### 4. Sprint activation and the "Start" button

The "Start" button behavior is mode-dependent:

| Mode | "Start" label | Behavior |
|---|---|---|
| Directed | Start | Transitions sprint to active immediately |
| Supervised | Promote to active | Confirms queue bypass, then transitions |
| Autonomous | Hidden | Agent owns activation; button not shown |

In all modes, activating a sprint while another sprint is already active is
rejected by the API with a clear error. Only one sprint may be active per
project at a time.

### 5. Auto-advance contract

In Supervised and Autonomous modes, the agent runner is responsible for
activating the next sprint after one completes. The orchestrator must:

- On sprint completion, query the next planned sprint by `order_index` (in
  Supervised mode) or by its own reasoning (in Autonomous mode).
- Transition that sprint to active via the standard sprint transition API.
- Persist a `sprint.auto_advanced` event before beginning work on the new
  sprint.

In Directed mode, the agent must not call the sprint transition API for
activation. Auto-advance is disabled entirely.

### 6. Schema additions

```sql
-- autonomy_level on projects (migration)
ALTER TABLE projects ADD COLUMN autonomy_level TEXT NOT NULL DEFAULT 'supervised';

-- decision_gates table (new)
CREATE TABLE decision_gates (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    sprint_id TEXT NOT NULL REFERENCES sprints(id),
    raised_at TEXT NOT NULL,
    conflict_description TEXT NOT NULL,
    suggested_order TEXT NOT NULL,   -- JSON array of sprint IDs
    suggested_reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    resolved_at TEXT,
    resolved_by TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX idx_decision_gates_project ON decision_gates(project_id, status);
```

## Consequences

- The orchestrator must read `autonomy_level` before making any sequencing
  decision and must not advance sprints in Directed mode.
- The sprint transition API must enforce the one-active-sprint-per-project
  constraint at the persistence layer, not just in application logic.
- Decision gate creation and polling become part of the agent runner contract
  in Supervised mode (see ADR-0001).
- The dashboard must adapt affordances (Start button, queue reorder controls)
  based on `autonomy_level`.
- Future sprint slices must not land agent sequencing logic without reading
  `autonomy_level` first.
- Auto-advance in Autonomous mode means the agent can modify sprint status
  without human action; the audit trail depends on the `sprint.auto_advanced`
  event being reliably persisted.

## References

- `docs/specs/engine-design-v3.md`
- `docs/adr/ADR-0001-runner-session-backend-contract.md`
- `foreman/dashboard_service.py`
- `foreman/store.py`
- `frontend/src/components.jsx` (SprintList, sprint card actions)
