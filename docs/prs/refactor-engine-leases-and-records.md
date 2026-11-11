# refactor/engine-leases-and-records

## Summary

Sprint 57 slice 2a. More of `foreman/orchestrator.py` moved into
`foreman/engine/`, text-exact, this time including two pieces that own
state.

## Scope

- `engine/leasing.py`: `TaskLeases(store, holder_id)` with `acquire`,
  `renew`, `release`, `forget`, `start_heartbeat`, `stop_heartbeat`, `close`,
  `holds`, `token_for`. The orchestrator holds one as `self.leases`.
- `engine/records.py`: `RunRecords(store, notifier)` with
  `create_running_run`, `create_system_run`, `complete_run`, `emit_event`,
  `emit_attention_needed`, `attention_trigger_for_block`,
  `session_id_from_events`, `select_project_system_task`; `new_id`. The
  orchestrator holds one as `self.records`.
- `engine/branch_sync.py`: `task_working_dir`, `context_mirror_dirs`,
  `prepare_task_branch_for_step`, `refresh_task_branch`, feedback-note
  helpers.
- `engine/prompts.py`, `engine/gates.py`: stateless helpers;
  `quota_run_result` joins `engine/results.py`.
- Tests call the new names; four now-unused orchestrator constructions in
  tests were removed.

## Files changed

`foreman/orchestrator.py`, `foreman/engine/` (five new modules, one
extended), `tests/test_orchestrator.py`, `tests/test_serve.py`,
`tests/test_notifications.py`, changelog, sprint.

## Migrations

None.

## Risks

Behaviour-preserving by construction; the suite (1064 tests) passes after
each move.

## Tests

Full Python suite and `ruff check`.

## Acceptance criteria satisfied

Slice 2a as written in `docs/sprints/current.md`.

## Follow-ups

Slice 2b.
