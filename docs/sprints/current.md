# Current Sprint

- Sprint: `sprint-06-claude-runner`
- Status: active
- Goal: implement the native Claude Code runner backend for Foreman
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Included tasks

1. `[todo]` Define the runner interface contract
   Deliverable: a `Runner` protocol or ABC that specifies session handling,
   event capture, and retry behavior for agent backends.

2. `[todo]` Implement Claude Code runner session handling
   Deliverable: the Claude Code runner can invoke Claude with a prompt and
   capture session state for persistence.

3. `[todo]` Implement event capture and run persistence
   Deliverable: a persisted run with structured events from one Claude task
   execution.

## Excluded from this sprint

- native Codex runner implementation
- monitoring CLI surfaces
- dashboard and web implementation
- schema migration framework work

## Acceptance criteria

- Claude Code runner implements the runner interface
- Runs are persisted with structured events
- Session state is captured for retry/resume scenarios
- docs and validation remain good enough for a fresh autonomous agent to pick
  the next slice without extra human context

## Known risks

- Claude Code API surface may differ from spec assumptions
- session persistence semantics need clarification against actual Claude
  behavior
- event schema may need iteration based on real execution patterns

## Demo checklist

- show a task executing through the Claude runner
- show a persisted run with captured events in SQLite
- show repo validation passing after the runner slice lands
