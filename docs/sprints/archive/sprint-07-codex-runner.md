# Sprint Archive: sprint-07-codex-runner

- Sprint: `sprint-07-codex-runner`
- Status: completed
- Goal: execute shipped Codex roles through a native Foreman runner with
  persisted runs, sessions, and structured events
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
- Completed: 2026-03-30

## Final task statuses

1. `[done]` Implement the first concrete Codex runner backend
   Deliverable: `foreman/runner/codex.py` can execute one role prompt, return
   normalized run results, and preserve session IDs for persistent roles.

2. `[done]` Integrate native Codex runner selection into the orchestrator path
   Deliverable: Foreman can execute Codex-backed roles without an injected
   scripted test executor while preserving run, event, and retry semantics.

3. `[done]` Add runner coverage for success, session reuse, approval handling,
   and infrastructure failure behavior
   Deliverable: tests prove the Codex runner returns normalized results and
   integrates cleanly with orchestrator execution alongside the existing
   Claude backend.

## Deliverables

- `foreman/runner/codex.py` — CodexRunner with JSON-RPC protocol support
- `foreman/runner/__init__.py` — CodexRunner export
- `foreman/orchestrator.py` — CodexRunner in default agent_runners
- `tests/test_runner.py` — 10 Codex runner tests

## Demo notes

- `./venv/bin/python -m pytest tests/test_runner.py -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- All 83 tests pass

## Follow-ups moved forward

- `sprint-08-monitoring-cli`: add `foreman board`, `foreman watch`,
  `foreman history`, and `foreman cost`
- backlog: dashboard implementation, first ADR for runner session handling
