# Current Sprint

- Sprint: `sprint-09-runner-session-backend-adr`
- Status: active
- Goal: capture the first accepted ADR for runner session handling, approval
  policy, and backend contract boundaries now that native runners and
  monitoring CLI surfaces exist
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `foreman/runner/`
  - `foreman/orchestrator.py`
  - `foreman/cli.py`

## Included tasks

1. `[todo]` Write the first accepted runner session ADR
   Deliverable: an ADR in `docs/adr/` defines session creation, reuse,
   invalidation, and persistence expectations across Claude and Codex roles.

2. `[todo]` Document approval policy and backend contract boundaries
   Deliverable: the ADR states what the shared runner protocol guarantees,
   what remains backend-specific, and how approval or pricing gaps should be
   represented in persisted state.

3. `[todo]` Align architecture and roadmap docs to the accepted ADR
   Deliverable: repo memory references the ADR as an active implementation
   constraint for future runner, monitoring, and dashboard slices.

## Excluded from this sprint

- dashboard and web implementation
- live streaming transport work beyond documenting the boundary
- schema migration framework work

## Acceptance criteria

- an accepted ADR exists in `docs/adr/` for runner sessions and backend
  contract boundaries
- `docs/STATUS.md`, `docs/ARCHITECTURE.md`, and `docs/ROADMAP.md` reference
  the ADR as a current implementation constraint
- current runtime behavior is documented accurately without backfilling
  speculative guarantees
- docs and validation remain good enough for a fresh autonomous agent to pick
  the next slice without extra human context

## Known risks

- the current Claude and Codex runner paths already differ in small but real
  ways; the ADR needs to document those differences without freezing accidental
  quirks as permanent product policy
- monitoring CLI output now exposes backend telemetry gaps directly, so the ADR
  needs to stay explicit about zero-USD token runs and approval semantics

## Demo checklist

- show the accepted ADR path in `docs/adr/`
- show at least one repo doc referencing the ADR as an active constraint
- show repo validation passing after the runner ADR slice lands
