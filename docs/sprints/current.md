# Current Sprint

- No active implementation sprint.
- Last completed sprint: `sprint-46-completion-truth-hardening`
- Last merged branch: `fix/backend-correctness-hardening` at `b396fda`
- Planning branch: `docs/integrate-review-plan`
- Next implementation sprint: `sprint-47-review-phase-0-correctness`
- Existing queued SQLite sprint: `sprint-47-active-run-lease-and-heartbeat-recovery`
  is deferred until review Phase 0 is complete.

## Review Integration

`docs/specs/review.md` has been read as a backend implementation review and
completion roadmap. It does not supersede `docs/specs/engine-design-v3.md` for
product behavior or `docs/mockups/foreman-mockup-v6.html` for UI hierarchy.

Phase 0 is the next sprint because it contains correctness bugs that can break
normal engine operation. Two Phase 0 issues are already fixed on `main`:

- `engine.role_policy` is emitted after run creation and belongs to the correct
  workflow step run.
- merge conflicts now return and route through the explicit `conflict` outcome.

The remaining Phase 0 tasks should be implemented before the older lease
recovery sprint resumes:

1. Fix `signal.task_created` persistence so `engine.task_created` is attached
   to the active run instead of referencing an unbound local.
2. Import `uuid4` for `foreman waive-merge` and cover the command end to end.
3. Make dashboard human/stop events FK-safe by sharing a synthetic-run helper
   and using the latest run for human messages.
4. Move dashboard run process tracking out of per-request service instances,
   terminate spawned runs on Stop, and expose `agent_running` in project
   payloads.
5. Restrict completion-evidence construction to decision roles and invalidate
   cached evidence when the task branch head changes.
6. Align dashboard task cancellation with CLI cancellation by clearing workflow
   resume fields and setting `completed_at`.
7. Remove the dead `foreman/executor.py` path and its tests.

## Most Recent Completed Sprint Outcome

Sprint 46 is complete. Its backend deliverables are all present on `main`,
including:

- structured completion evidence in the orchestrator and task store
- false-positive completion regression coverage
- merge-time weak-completion guarding
- completion-truth ADR and docs
- reviewer prompt hardening with engine-produced evidence

The main issue at sprint close was not unfinished feature code. It was
operational drift: a hidden host-side `foreman run foreman` process continued
running after the sprint was effectively done, leaving stale `running` rows and
continued repo or SQLite activity that was difficult to inspect from the normal
sandboxed shell.

## Closeout Notes

- All sprint-46 tasks are `done` in SQLite.
- Sprint `sprint-46-completion-truth-hardening` is `completed` in SQLite.
- There are no remaining `running` rows in `runs`.
- The stale hidden host-side Foreman and Claude processes were identified and
  stopped before sprint closeout.

## Why No New Active Sprint Yet

Before starting more autonomous work, Foreman needs the open Phase 0 review
bugs fixed and covered by regression tests. The old queued lease-recovery work
is still valuable, but it now follows the review's correctness pass.

## Next Planned Sprint

- Sprint: `sprint-47-review-phase-0-correctness`
- Branch: `fix/review-phase0-correctness`
- Deliverable: all remaining Phase 0 fixes from `docs/specs/review.md` with
  regression tests, full unit suite where the local venv is available, and
  updated PR/checkpoint docs.
