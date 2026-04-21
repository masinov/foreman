# PR Summary: feat/sprint-007-t1-gate-schema

## Summary

- Add `Gate` model and `gates` SQLite table for human-gate pause points
- Wire full CRUD in `ForemanStore` (`save_gate`, `get_gate`, `list_gates`, `list_pending_gates`)
- Add migration 5: `gates` table with `sprint_id`, `type`, `payload`, `status`, `resolved_at`
- Add round-trip tests for all gate fields and filter combinations

## Scope

- `foreman/models.py` — `Gate` dataclass (`sprint_id`, `task_id`, `type`, `payload`, `status`, `resolved_at`)
- `foreman/migrations.py` — migration 5: `gates` table
- `foreman/store.py` — `_row_to_gate`, `save_gate`, `get_gate`, `list_gates`, `list_pending_gates`; rename `decision_gate` row mapper to `_row_to_decision_gate` to avoid collision
- `tests/test_store.py` — `test_gate_round_trip_all_fields_and_crud`

## Files changed

- `foreman/models.py`
- `foreman/migrations.py`
- `foreman/store.py`
- `tests/test_store.py`

## Migrations

- Migration 5: `add gates table for human-gate pause points`
  - `gates(id, project_id, sprint_id, task_id, type, payload_json, status, raised_at, resolved_at, resolved_by)`
  - `idx_gates_project_status(project_id, status)`
  - `idx_gates_sprint(sprint_id)`

## Risks

- The `gates` table is structurally independent from the `tasks` table; task-scoped `blocked` status and the gate record are separate concerns that sprint-007-t2 must keep in sync when the orchestrator creates a gate.

## Tests

- `./venv/bin/python -m pytest tests/test_migrations.py tests/test_store.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Acceptance criteria satisfied

- [x] `gates` table with `sprint_id`, `type`, `payload`, `status`, `resolved_at`
- [x] `Gate` model round-trips all fields including `task_id` and `resolved_by`
- [x] `list_gates` supports `status` and `sprint_id` filters
- [x] `list_pending_gates` shortcut for the pending-gate polling use case
- [x] Migration integrity tests pass (consecutive versions, non-empty descriptions/SQL)

## Follow-ups

- sprint-007-t2: orchestrator emits `gate_opened` event and creates a `Gate` record when `_builtin:human_gate` step is encountered
- sprint-007-t3: `GET /projects/:id/gates` API endpoint
- sprint-007-t4: `POST /gates/:id/resolve` to approve/reject/dismiss
- sprint-007-t5: `GateBanner` React component
- sprint-007-t6: frontend polls for pending gates