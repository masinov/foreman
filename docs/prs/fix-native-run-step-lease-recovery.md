## Summary

Hardens native workflow step ownership and crash recovery after stranded
`review` runs left SQLite showing `running` work with no live Foreman process.

## Scope

- persist `task.workflow_current_step` before entering native steps
- stream native runner events into SQLite immediately instead of buffering them
  until step return
- base stale-run recovery on the latest persisted event timestamp
- separate active-run recovery timeout from the full per-run time limit

## Files changed

- `foreman/orchestrator.py`
- `foreman/store.py`
- `tests/test_orchestrator.py`
- `docs/STATUS.md`
- `docs/sprints/current.md`

## Migrations

- none

## Risks

- stale detection still uses a time window, not a true lease heartbeat owned by
  a live runner process
- agent-executor injections used in tests still return buffered results because
  the streaming path is native-runner specific

## Tests

- `./venv/bin/python -m pytest tests/test_orchestrator.py -q`
- `./venv/bin/python -m pytest tests/test_store.py -q`
- `./venv/bin/python -m py_compile foreman/orchestrator.py foreman/store.py`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Acceptance criteria satisfied

- early native runner events survive a mid-step crash and remain visible in
  SQLite
- tasks persist the active workflow step before native execution starts
- stale recovery follows the latest persisted run activity instead of the
  original run start time

## Follow-ups

- add an explicit run lease/heartbeat record instead of inferring liveness from
  the events table
- rerun the blocked sprint-46 tasks against the repaired runtime path
