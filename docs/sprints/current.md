# Current Sprint

- Sprint: `sprint-26-history-lifecycle-expansion`
- Status: done
- Goal: extend retention and cleanup policy beyond `events` so `runs` and
  stored prompts can be pruned safely on top of the migration framework
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/store.py`
  - `foreman/migrations.py`
  - `foreman/orchestrator.py`
  - `tests/test_run_retention.py`

## Included tasks

1. `[done]` Add migration 2 to `foreman/migrations.py`
   Deliverable: `idx_runs_project_completed ON runs(project_id, completed_at)`
   added as a safe additive migration; `test_partial_db_upgraded_to_latest`
   now passes.

2. `[done]` Add `ForemanStore.prune_old_runs()`
   Deliverable: deletes terminal runs older than a cutoff; cascades to their
   dependent events in one transaction; protects runs whose task is still
   `blocked` or `in_progress`.

3. `[done]` Add `ForemanStore.strip_old_run_prompts()`
   Deliverable: nulls `prompt_text` on old terminal runs without deleting the
   run record or its telemetry; scoped by project and cutoff.

4. `[done]` Wire lifecycle expansion into the orchestrator
   Deliverable: `prune_old_history()` replaces `prune_old_events()` as the
   startup pruning entrypoint; reads `run_retention_days` and
   `prompt_retention_days` from project settings alongside
   `event_retention_days`; emits `engine.run_pruned` and
   `engine.prompt_stripped` lifecycle events.

5. `[done]` Add `tests/test_run_retention.py`
   Deliverable: 19 tests covering basic deletion, active-work protection,
   cascade event deletion, prompt stripping, telemetry preservation, and
   migration 2 index existence.

## Excluded from this sprint

- `foreman db migrate` CLI surface
- browser-driven end-to-end dashboard validation
- `task_selection_mode="autonomous"` orchestrator implementation

## Acceptance criteria

- `prune_old_runs` deletes terminal runs and their events; blocked/in-progress
  task runs are preserved regardless of age
- `strip_old_run_prompts` nulls prompt text while preserving run records and
  telemetry
- migration 2 index exists after fresh install and after incremental upgrade
  from version 1
- `test_partial_db_upgraded_to_latest` passes (was previously skipped)
- all 188 tests pass
