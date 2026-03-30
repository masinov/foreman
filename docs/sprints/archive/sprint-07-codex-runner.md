# Sprint Archive: sprint-07-codex-runner

- Sprint: `sprint-07-codex-runner`
- Status: completed
- Goal: execute Codex-backed roles through a native Foreman runner with
  persisted run metadata, session handling, and structured events
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Final task statuses

1. `[done]` Implement the first concrete Codex runner backend
   Deliverable: `foreman/runner/codex.py` can execute one role prompt, start
   or resume a Codex thread, normalize streamed events, and preserve the
   resumed thread id for persistent roles.

2. `[done]` Integrate native Codex runner selection into the orchestrator path
   Deliverable: Foreman can execute Codex-backed roles without an injected
   scripted executor while preserving run, event, retry, and human-gate
   resume semantics.

3. `[done]` Add runner coverage for success, session reuse, approval handling,
   and infrastructure failure behavior
   Deliverable: tests prove the Codex runner returns normalized results and
   integrates cleanly with orchestrator execution alongside the existing
   Claude backend.

## Deliverables

- native Codex JSON-RPC runner over `codex app-server`
- automatic response handling for Codex command, file-change, and permission
  approval requests
- Codex token-usage capture and structured event mapping into Foreman runs
- orchestrator default backend map with both Claude and Codex runners
- immediate human-gate resume for native backends when the repo runtime is
  available, with deferred persistence retained for missing backends or repo
  paths
- Codex runner unit coverage plus expanded orchestrator integration coverage

## Demo notes

- `./venv/bin/python -m unittest tests.test_runner_codex tests.test_runner_claude tests.test_orchestrator -v`
- `./venv/bin/python -m unittest discover -s tests -v`

## Follow-ups moved forward

- `sprint-08-monitoring-cli`: add `foreman board`, `watch`, `history`, and
  `cost`
- backlog: runner session and backend ADR, dashboard implementation, security
  review workflow variant, and event-retention pruning
