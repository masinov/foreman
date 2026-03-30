# Sprint Archive: sprint-09-runner-session-backend-adr

- Sprint: `sprint-09-runner-session-backend-adr`
- Status: completed
- Goal: capture the first accepted ADR for runner session handling, approval
  policy, and backend contract boundaries now that native runners and
  monitoring CLI surfaces exist
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `foreman/runner/`
  - `foreman/orchestrator.py`

## Final task statuses

1. `[done]` Write the first accepted runner session ADR
   Deliverable: `docs/adr/ADR-0001-runner-session-backend-contract.md`
   defines session creation, reuse, persistence scope, and explicit current
   gaps.

2. `[done]` Document approval policy and backend contract boundaries
   Deliverable: the ADR records the split between workflow approvals and
   runner transport approvals plus the current Claude and Codex telemetry
   differences.

3. `[done]` Align architecture and roadmap docs to the accepted ADR
   Deliverable: repo memory now cites ADR-0001 as an active implementation
   constraint and rolls the next sprint to dashboard implementation.

## Deliverables

- accepted ADR `ADR-0001-runner-session-backend-contract.md`
- documented current gap for cross-invocation persistent-session reload from
  SQLite
- repo-memory rollover from the runner ADR sprint to the dashboard sprint
- branch checkpoint and PR summary for this accepted decision slice

## Demo notes

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-10-dashboard-implementation`: build the first interactive dashboard
  slice aligned to the mockup while honoring ADR-0001
- backlog: security review workflow variant, event-retention pruning,
  optional PR or checkpoint automation, and multi-project dashboard polish
