# Current Sprint

- Sprint: `sprint-13-persistent-session-reload`
- Status: active
- Goal: reload the last persisted native runner session from SQLite on fresh
  orchestrator invocations so role-level session persistence survives process
  restarts
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/adr/ADR-0001-runner-session-backend-contract.md`
  - `foreman/orchestrator.py`
  - `foreman/store.py`
  - `foreman/runner/claude_code.py`
  - `foreman/runner/codex.py`

## Included tasks

1. `[todo]` Add persisted-session lookup in the store and orchestrator
   Deliverable: the orchestrator can retrieve the latest compatible
   `session_id` for the same `task + role + backend` when role policy allows
   session persistence.

2. `[todo]` Reuse persisted sessions across fresh orchestrator invocations
   Deliverable: Claude Code and Codex native runs resume the prior backend
   session after process restart instead of always starting a new session.

3. `[todo]` Add regression coverage for cross-invocation session reuse
   Deliverable: tests cover fresh-process session reuse, human-gate resume, and
   roles with `session_persistence = false`.

## Excluded from this sprint

- dashboard streaming transport
- event-retention pruning
- security review workflow variant
- backend preflight health checks

## Acceptance criteria

- a fresh orchestrator invocation reuses the last compatible native session for
  persistent roles
- roles with `session_persistence = false` still start fresh sessions
- Claude Code and Codex both have automated coverage for the new behavior
