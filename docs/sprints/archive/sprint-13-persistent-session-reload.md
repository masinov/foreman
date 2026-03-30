# Sprint Archive: sprint-13-persistent-session-reload

- Sprint: `sprint-13-persistent-session-reload`
- Status: completed
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

## Final task statuses

1. `[done]` Add persisted-session lookup in the store and orchestrator
   Deliverable: the orchestrator can retrieve the latest compatible
   `session_id` for the same `task + role + backend` when role policy allows
   session persistence.

2. `[done]` Reuse persisted sessions across fresh orchestrator invocations
   Deliverable: Claude Code and Codex native runs resume the prior backend
   session after process restart instead of always starting a new session.

3. `[done]` Add regression coverage for cross-invocation session reuse
   Deliverable: tests cover fresh-process session reuse, human-gate resume, and
   roles with `session_persistence = false`.

## Deliverables

- `ForemanStore.get_latest_session_id(...)` for task and role and backend
  scoped lookup of the latest non-empty persisted session
- orchestrator-native runner execution now seeds persistent roles from that
  stored session on fresh process starts
- fresh-process regression coverage for Claude Code session reuse
- fresh-process regression coverage for Codex session reuse
- explicit negative coverage proving non-persistent reviewer roles still start
  fresh sessions even when a prior `session_id` exists in SQLite
- repo-memory rollover from session continuity to dashboard live transport

## Demo notes

- `./venv/bin/python -m unittest tests.test_store tests.test_orchestrator -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-14-dashboard-streaming-transport`: replace polling-only dashboard
  refresh with a live transport boundary
- backlog: engine-level database discovery, security review workflow variant,
  event-retention pruning, optional PR or checkpoint automation, and backend
  preflight health checks
