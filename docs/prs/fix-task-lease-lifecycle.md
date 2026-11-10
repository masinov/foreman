# PR Summary: fix/task-lease-lifecycle

## Summary

- Sprint 55 slice 5. A task's lease now lasts exactly as long as the engine
  is working on the task.

## Scope

- `foreman/task_lease.py`: `TaskLeaseHeartbeat`, a daemon thread with its
  own connection that renews one lease on a timer.
- `foreman/orchestrator.py`: `run_task` starts and stops the heartbeat;
  `_forget_task_lease` replaces three ad-hoc token pops; stale-run recovery
  re-acquires a lease this engine held; the workflow loop releases the
  lease of a task it leaves `blocked`.
- Not in scope: recovery resetting the task to its entry step; a lease for
  `resume_human_gate`.

## Files changed

- `foreman/task_lease.py` (new), `foreman/orchestrator.py`
- `tests/test_leases.py`, `tests/test_orchestrator.py`
- `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- One more thread and SQLite connection per running task; it writes every
  20 seconds. In-memory databases get no heartbeat.
- A heartbeat that cannot reach the database three times in a row stops;
  the orchestrator's own renewal between steps then decides.

## Tests

- `python -m unittest discover -s tests`: 1031 pass, 1 skipped (7 new,
  four of them timing real lease expiry)
- `ruff check foreman tests scripts`: clean

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A step longer than the lease keeps the lease.
- Recovery at the start of `run_task` leaves the engine holding the task.
- A gate-blocked task holds no lease and no heartbeat.

## Follow-ups

- Slice 6: approve and deny through the engine.
