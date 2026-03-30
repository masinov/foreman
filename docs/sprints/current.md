# Current Sprint

- Sprint: `sprint-17-native-backend-preflight-checks`
- Status: active
- Goal: fail fast when required Claude Code or Codex native backend
  prerequisites are unavailable or misconfigured
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/runner/claude_code.py`
  - `foreman/runner/codex.py`
  - `foreman/orchestrator.py`
  - `tests/test_runner_claude.py`
  - `tests/test_runner_codex.py`
  - `tests/test_orchestrator.py`

## Included tasks

1. `[todo]` Validate native backend availability before execution
   Deliverable: Claude Code and Codex runs fail with explicit preflight errors
   when required executables or startup contracts are missing.

2. `[todo]` Persist and surface preflight failures cleanly
   Deliverable: orchestrator and runner-facing error paths distinguish
   backend preflight failure from mid-run agent failure.

3. `[todo]` Document backend startup assumptions and operator recovery
   Deliverable: repo docs explain required binaries, startup assumptions, and
   what operators should do when preflight fails.

## Excluded from this sprint

- event-retention pruning
- multi-user dashboard concerns
- `foreman watch` live-tail alignment
- migration framework work

## Acceptance criteria

- missing or misconfigured native backends fail before long-running execution
  begins
- automated tests cover Claude Code and Codex preflight failure modes
- docs explain backend assumptions and operator recovery steps clearly enough
  for fresh agents and operators
