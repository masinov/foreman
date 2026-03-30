# Current Sprint

- Sprint: `sprint-04-context-projection`
- Status: active
- Goal: project runtime context from SQLite into `.foreman/context.md` and
  `.foreman/status.md` before and after workflow activity
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Included tasks

1. `[todo]` Implement store-driven context rendering for project, sprint, and
   task state
   Deliverable: Foreman can render `.foreman/context.md` and
   `.foreman/status.md` from persisted SQLite records without treating those
   files as committed project state.

2. `[todo]` Integrate automatic context projection into orchestrator lifecycle
   and `_builtin:context_write`
   Deliverable: the orchestrator writes fresh context before agent runs and
   after task completion, and workflows can explicitly invoke the same
   projection path through `_builtin:context_write`.

3. `[todo]` Add coverage for context projection and runtime updates
   Deliverable: tests prove projected files reflect active sprint and task
   state and remain under the gitignored `.foreman/` directory.

## Excluded from this sprint

- native Claude Code and Codex runner implementations
- human-gate approve and deny CLI commands
- dashboard and monitoring CLI surfaces
- schema migration framework work

## Acceptance criteria

- `.foreman/context.md` and `.foreman/status.md` are projected from SQLite
  records, not hand-authored markdown
- orchestrator activity refreshes runtime context before agent execution and
  after task completion
- explicit workflow context writes reuse the same projection implementation
- docs and validation remain good enough for a fresh autonomous agent to pick
  the next slice without extra human context

## Known risks

- projected markdown needs stable formatting without ossifying the future
  monitoring UI or API contract too early
- runtime context writes need to stay engine-owned without clobbering useful
  debugging signals during workflow execution

## Demo checklist

- show `.foreman/context.md` and `.foreman/status.md` written from persisted
  project data
- show orchestrator or built-in driven context refresh updating those files
- show repo validation passing after the context projection slice lands
