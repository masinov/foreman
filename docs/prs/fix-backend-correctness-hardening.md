# PR Summary — fix/backend-correctness-hardening

## Summary

Tightens backend correctness after the supervised Foreman runs by reconciling a
stale bug inventory with current `main`, fixing the confirmed streamed builtin
event schema gap, and adding regression coverage for strict outcome,
crash-recovery, and lease-safety behavior.

## Scope

- Persist `schema_version` on immediately streamed builtin events.
- Return and route merge conflicts as the explicit `conflict` outcome instead
  of generic `failure`.
- Recover cleanly from a post-merge-conflict checkout on `main` by checking
  the task branch out before the next directed developer step.
- Preserve strict unknown-outcome handling while routing reviewer and security
  reviewer outcomes through reviewer-decision normalization.
- Allow proof status to pass on small but real diffs when tests pass and code
  review explicitly approves, avoiding deadlocks caused by heuristic criteria
  matching misses.
- Update outcome tests to assert unknown agent outcomes become `error`.
- Update reviewer decision tests so informal approvals do not pass review.
- Update crash-recovery tests to assert lease tokens are not persisted.
- Add lease regression coverage for unique active-resource indexing and
  monotonic fencing-token increments across lease reacquisition.
- Preserve the backend bug triage as a checkpoint instead of a spec file.

## Files Changed

- `tests/test_outcomes.py`
- `foreman/builtins.py`
- `foreman/orchestrator.py`
- `foreman/outcomes.py`
- `tests/test_events.py`
- `tests/test_leases.py`
- `tests/test_orchestrator.py`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/checkpoints/2026-04-29-backend-correctness-bug-triage.md`
- `docs/prs/fix-backend-correctness-hardening.md`

## Migrations

No new migration. Existing migration 9 already provides the unique active lease
index; this branch adds regression coverage for it.

## Risks

- The remaining settings-validation wiring gap is documented as a follow-up;
  this branch does not centralize all runtime settings access.
- The branch validates targeted backend safety behavior, not a new autonomous
  Foreman run.

## Tests

- `./venv/bin/python -m pytest tests/test_outcomes.py tests/test_events.py tests/test_leases.py tests/test_orchestrator.py::BuiltinTranscriptLoggingTests::test_persisted_streamed_builtin_events_include_schema_version -q`
- `./venv/bin/python -m pytest tests/test_workflows.py -q`
- `./venv/bin/python -m pytest tests/test_orchestrator.py tests/test_store.py tests/test_migrations.py tests/test_workflows.py tests/test_events.py tests/test_outcomes.py tests/test_leases.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile foreman/orchestrator.py foreman/builtins.py foreman/outcomes.py foreman/events.py foreman/store.py`

## Acceptance Criteria Satisfied

- Streamed builtin events can be audited with schema version metadata.
- Unknown agent outcomes do not pass through to arbitrary workflow triggers.
- Informal reviewer text cannot become merge approval.
- Crash-recovery event payloads do not expose lease tokens.
- Lease reacquisition increments fencing tokens.
- SQLite enforces one active lease per project resource.
- Merge conflicts go through the explicit conflict transition and back through
  development/review.
- Reviewer approvals still route after unknown generic outcomes became safe
  errors.

## Follow-Ups

- Centralize `ProjectSettings.from_raw(...)` at runtime boundaries and stop
  silently defaulting invalid settings in local helper functions.
