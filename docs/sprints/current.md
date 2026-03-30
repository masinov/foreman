# Current Sprint

- Sprint: `sprint-07-codex-runner`
- Status: active
- Goal: execute shipped Codex roles through a native Foreman runner with
  persisted runs, sessions, and structured events
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Included tasks

1. `[todo]` Implement the first concrete Codex runner backend
   Deliverable: `foreman/runner/codex.py` can execute one role prompt, return
   normalized run results, and preserve session IDs for persistent roles.

2. `[todo]` Integrate native Codex runner selection into the orchestrator path
   Deliverable: Foreman can execute Codex-backed roles without an injected
   scripted test executor while preserving run, event, and retry semantics.

3. `[todo]` Add runner coverage for success, session reuse, approval handling,
   and infrastructure failure behavior
   Deliverable: tests prove the Codex runner returns normalized results and
   integrates cleanly with orchestrator execution alongside the existing
   Claude backend.

## Excluded from this sprint

- monitoring CLI surfaces beyond approve and deny
- dashboard and web implementation
- schema migration framework work

## Acceptance criteria

- the orchestrator can execute a Codex-backed role through a native runner
  implementation
- persistent Codex sessions can be reused across eligible workflow steps
- runner failures are normalized into durable run and event history
- docs and validation remain good enough for a fresh autonomous agent to pick
  the next slice without extra human context

## Known risks

- the Codex runner must not leak backend-specific quirks into the shared
  orchestrator model
- session lifecycle and retry behavior need to line up with the spec without
  diverging from the now-shipped Claude runner semantics

## Demo checklist

- show one Codex-backed role executing through the native runner
- show persisted run metadata and structured events from that execution
- show repo validation passing after the runner slice lands
