# Sprint Archive: sprint-06-claude-runner

- Sprint: `sprint-06-claude-runner`
- Status: completed
- Goal: execute shipped Claude Code roles through a native Foreman runner with
  persisted runs, sessions, and structured events
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Final task statuses

1. `[done]` Implement the first concrete Claude Code runner backend
   Deliverable: `foreman/runner/claude_code.py` can execute one role prompt,
   return normalized run results, and preserve session IDs for persistent
   roles.

2. `[done]` Integrate native runner selection into the orchestrator path
   Deliverable: Foreman can execute shipped Claude-backed roles without an
   injected scripted test executor while preserving run, event, and retry
   semantics.

3. `[done]` Add runner coverage for success, session reuse, and infrastructure
   failure handling
   Deliverable: tests prove the Claude runner returns normalized results and
   integrates cleanly with orchestrator execution.

## Deliverables

- shared native runner config, event, and retry primitives
- defensive `FOREMAN_SIGNAL:` extraction for runner output
- Claude Code stream-json backend with command construction, session resume,
  cost tracking, and gate enforcement
- native orchestrator execution path for shipped Claude-backed roles
- runner and orchestrator coverage for success, session reuse, and retry
  exhaustion

## Demo notes

- `./venv/bin/python -m unittest tests.test_runner_claude tests.test_orchestrator -v`
- `./venv/bin/python -m unittest discover -s tests -v`

## Follow-ups moved forward

- `sprint-07-codex-runner`: implement the native Codex backend
- backlog: monitoring CLI, dashboard implementation, and the first runner ADR
