# PR Summary: feat/active-run-lease-heartbeat-recovery

## Summary

- Hardened active-run recovery around task lease liveness and native-runner
  heartbeat behavior.
- Used MiniMax M3 through Claude Code for the delegated implementation pass,
  with Codex supervising review, cleanup, validation, and merge readiness.

## Scope

- add periodic task-lease renewal inside native runner stream processing
- treat old task-lease heartbeats as stale holder evidence during recovery
- force-expire recovered task leases before resetting tasks to `todo`
- add focused regression coverage for recovery and heartbeat paths

## Files changed

- `foreman/orchestrator.py`
- `foreman/store.py`
- `tests/test_orchestrator.py`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `CHANGELOG.md`
- `docs/checkpoints/2026-06-12-active-run-lease-heartbeat-recovery.md`

## Migrations

- none

## Risks

- Native runner heartbeats are still driven by stream events; a backend that
  emits no events for longer than the active-run timeout can still be treated
  as stale.
- Recovery liveness uses a fixed one-minute heartbeat threshold for active
  leases.

## Tests

- `./venv/bin/python -m py_compile foreman/orchestrator.py foreman/store.py tests/test_orchestrator.py`
- `./venv/bin/python -m unittest tests.test_orchestrator -v`
- `./venv/bin/python -m unittest tests.test_leases -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `git diff --check`
- `./venv/bin/python -m unittest discover -s tests -v` - 518 tests passed

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- long native stream processing renews a task lease before step completion
- stale active-run recovery force-expires the recovered task lease
- crash-recovery events remain free of `lease_token`
- live active lease holders are not recovered while their heartbeat is recent

## Follow-ups

- Consider a persisted run-level heartbeat if Foreman later needs liveness for
  backends that stay silent for long periods.
