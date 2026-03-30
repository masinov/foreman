# Current Sprint

- Sprint: `sprint-05-human-gates`
- Status: active
- Goal: resume paused human-gate tasks through `foreman approve` and
  `foreman deny` with persisted workflow state
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Included tasks

1. `[done]` Add CLI commands for human-gate approval and denial
   Deliverable: operators can issue `foreman approve <task-id>` and
   `foreman deny <task-id>` against paused tasks in the SQLite store.

2. `[done]` Integrate workflow resume semantics for paused tasks
   Deliverable: a task paused by `_builtin:human_gate` can resume from its
   persisted workflow step with the recorded carried output and decision.

3. `[done]` Add coverage for pause, approve, deny, and resume behavior
   Deliverable: tests prove human-gate tasks block, persist resume metadata,
   and continue through the workflow after an explicit human decision.

## Excluded from this sprint

- native Claude Code and Codex runner implementations
- monitoring CLI surfaces beyond approve and deny
- dashboard and web implementation
- schema migration framework work

## Acceptance criteria

- `foreman approve` and `foreman deny` operate on paused human-gate tasks
- paused tasks resume from persisted workflow state instead of restarting from
  the workflow entry step
- approval and denial decisions are persisted with workflow and event history
- docs and validation remain good enough for a fresh autonomous agent to pick
  the next slice without extra human context

## Known risks

- human-gate resume has to interact cleanly with existing loop counts, carried
  output, and branch state without duplicating prior workflow steps
- CLI resume commands should not silently mutate tasks that are blocked for
  non-human-gate reasons

## Demo checklist

- show a task pause at `_builtin:human_gate`
- show `foreman approve` or `foreman deny` resuming that task from persisted
  state
- show repo validation passing after the human-gate slice lands
