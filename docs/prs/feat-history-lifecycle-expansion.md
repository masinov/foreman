# PR: feat/history-lifecycle-expansion

## Summary

Extends history retention beyond `events` to cover `runs` and stored prompt
text, and adds the second schema migration that activates the previously-skipped
incremental-upgrade test.

## Scope

- `foreman/migrations.py` — migration 2: `idx_runs_project_completed` index
- `foreman/store.py` — `prune_old_runs()`, `strip_old_run_prompts()`
- `foreman/orchestrator.py` — `prune_old_history()` replaces `prune_old_events()`
  as the startup pruning entrypoint; reads `run_retention_days` and
  `prompt_retention_days` in addition to `event_retention_days`
- `tests/test_run_retention.py` — 19 new store-level tests
- `tests/test_migrations.py` — `test_partial_db_upgraded_to_latest` now passes
- sprint and repo-memory docs updated

## Files changed

| File | Change |
|------|--------|
| `foreman/migrations.py` | migration 2 added |
| `foreman/store.py` | `prune_old_runs()`, `strip_old_run_prompts()` added |
| `foreman/orchestrator.py` | `prune_old_history()`, `_retention_cutoff()`, `_emit_pruned_event()` added |
| `tests/test_run_retention.py` | new |
| `docs/prs/feat-history-lifecycle-expansion.md` | new |
| `docs/sprints/current.md` | sprint-26 tasks |
| `docs/sprints/backlog.md` | sprint-26 removed from next-up |
| `docs/STATUS.md` | updated |
| `CHANGELOG.md` | updated |

## Migrations

Migration 2 adds `idx_runs_project_completed ON runs(project_id, completed_at)`.
This is a `CREATE INDEX IF NOT EXISTS` — safe to apply to existing databases,
no data migration required.

## New project settings

| Key | Type | Effect |
|-----|------|--------|
| `run_retention_days` | int | Hard-delete terminal runs (and their events) older than N days. Blocked/in-progress task runs are protected. |
| `prompt_retention_days` | int | Null out `prompt_text` on terminal runs older than N days. Run records and telemetry are preserved. |

Both settings are optional and independent. The existing `event_retention_days`
behavior is unchanged.

## Risks

- Run deletion cascades to events (FK). The store method deletes dependent
  events first within the same transaction before deleting the runs.
- `prune_old_events()` on the orchestrator is kept as a thin delegate to
  `prune_old_history()` so any external call sites continue to work.

## Tests

```
./venv/bin/python -m pytest tests/test_run_retention.py tests/test_migrations.py -v
# 36 passed (including test_partial_db_upgraded_to_latest, previously skipped)

./venv/bin/python -m pytest tests/ -x -q
# 188 passed
```

## Acceptance criteria satisfied

- `prune_old_runs` deletes old terminal runs and their events ✓
- `prune_old_runs` protects runs on blocked/in-progress tasks ✓
- `strip_old_run_prompts` nulls prompt text while preserving run records ✓
- migration 2 index exists after fresh install ✓
- `test_partial_db_upgraded_to_latest` now passes (was skipped) ✓
- all 188 tests pass ✓

## Follow-ups

- `foreman db migrate` CLI surface for operators to inspect schema version and
  apply pending migrations explicitly
- browser-driven end-to-end dashboard validation
- `task_selection_mode="autonomous"` orchestrator implementation
