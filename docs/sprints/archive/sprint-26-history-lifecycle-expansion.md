# Sprint Archive: sprint-26-history-lifecycle-expansion

- Sprint: `sprint-26-history-lifecycle-expansion`
- Status: completed
- Goal: extend retention and cleanup policy beyond `events` to cover `runs`
  and stored prompt text, using the migration framework as the safe upgrade path
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/store.py`
  - `foreman/migrations.py`
  - `foreman/orchestrator.py`
  - `tests/test_run_retention.py`

## Final task statuses

1. `[done]` Add migration 2
   Deliverable: `idx_runs_project_completed ON runs(project_id, completed_at)`
   as an additive, idempotent migration; `test_partial_db_upgraded_to_latest`
   now passes (was skipped while only one migration existed).

2. `[done]` Add `ForemanStore.prune_old_runs()`
   Deliverable: hard-deletes terminal runs older than a cutoff; cascades to
   their FK-dependent events in one transaction; preserves runs on
   blocked/in-progress tasks.

3. `[done]` Add `ForemanStore.strip_old_run_prompts()`
   Deliverable: nulls `prompt_text` on old terminal runs; run records, cost,
   token count, and duration are preserved.

4. `[done]` Wire lifecycle expansion into the orchestrator
   Deliverable: `prune_old_history()` is now the startup pruning entrypoint;
   reads `run_retention_days` and `prompt_retention_days` from project settings;
   emits `engine.run_pruned` and `engine.prompt_stripped` lifecycle events;
   backward-compatible `prune_old_events()` delegate preserved.

5. `[done]` Add `tests/test_run_retention.py`
   Deliverable: 19 tests across basic deletion, active-work protection,
   cascade event removal, prompt stripping, telemetry preservation, and
   migration 2 index existence.

## Deliverables

- `foreman/migrations.py` — migration 2 added
- `foreman/store.py` — `prune_old_runs()`, `strip_old_run_prompts()` added
- `foreman/orchestrator.py` — `prune_old_history()`, `_retention_cutoff()`,
  `_emit_pruned_event()` added
- `tests/test_run_retention.py` — 19 new tests
- branch `feat/history-lifecycle-expansion` merged to main

## Validation notes

- `./venv/bin/python -m pytest tests/test_run_retention.py tests/test_migrations.py -v` — 36 passed (0 skipped)
- `./venv/bin/python -m pytest tests/ -x -q` — 188 passed
- `./venv/bin/python scripts/validate_repo_memory.py` — passed

## Follow-ups moved forward

- browser-driven end-to-end dashboard validation
- `task_selection_mode="autonomous"` orchestrator implementation
- `foreman db migrate` CLI surface
