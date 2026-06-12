# Current Sprint

- Active implementation sprint: none; `sprint-47-review-phase-0-correctness`
  is merged.
- Branch: none for implementation work; docs closeout branch is
  `docs/phase0-closeout-status`.
- Local Foreman sprint: `sprint-review-phase-0-correctness` in `.foreman.db`
- Last completed sprint: `sprint-47-review-phase-0-correctness`
- Existing queued SQLite sprint: `sprint-47-active-run-lease-and-heartbeat-recovery`
  remains deferred until the immediate Minimax/worker-fleet smoke is reliable.

## Review Integration

`docs/specs/review.md` has been read as a backend implementation review and
completion roadmap. It does not supersede `docs/specs/engine-design-v3.md` for
product behavior or `docs/mockups/foreman-mockup-v6.html` for UI hierarchy.

Phase 0 is the next sprint because it contains correctness bugs that can break
normal engine operation. Two Phase 0 issues are already fixed on `main`:

- `engine.role_policy` is emitted after run creation and belongs to the correct
  workflow step run.
- merge conflicts now return and route through the explicit `conflict` outcome.

The remaining Phase 0 tasks were implemented on `fix/review-phase0-correctness`
and fast-forward merged to `main` at `5883075`:

1. Fixed `signal.task_created` persistence so `engine.task_created` is attached
   to the active run instead of referencing an unbound local.
2. Imported `uuid4` for `foreman waive-merge` and covered the command end to end.
3. Made dashboard human/stop events FK-safe by sharing a synthetic-run helper
   and using the latest run for human messages.
4. Moved dashboard run process tracking out of per-request service instances,
   terminate spawned runs on Stop, and expose `agent_running` in project
   payloads.
5. Restricted completion-evidence construction to decision roles and invalidates
   cached evidence when the task branch head changes.
6. Aligned dashboard task cancellation with CLI cancellation by clearing workflow
   resume fields and setting `completed_at`.
7. Removed the dead `foreman/executor.py` path and its tests.
8. Cleared stale validation blockers by updating signal-parser and workflow
   count expectations, making `reviewed_codex.py` tolerate read-only
   `.codex/run` during import, and letting optional e2e tests skip when
   `pytest` is not installed.

## Validation Notes

Passing focused validation:

- `./venv/bin/python -m unittest tests.test_orchestrator.AgentSignalPersistenceTests tests.test_orchestrator.EvidenceCachingTests -v`
- `./venv/bin/python -m unittest tests.test_dashboard.DashboardApproveDenyIntegrationTests.test_message_endpoint_creates_synthetic_run_for_runless_task tests.test_dashboard.DashboardSprintLifecycleTests.test_stop_agent_blocks_in_progress_tasks tests.test_dashboard.DashboardSprintTaskBacklogTests.test_cancel_task_sets_cancelled_status tests.test_dashboard.DashboardTier2Tests.test_start_and_stop_agent_registry_survives_service_instances -v`
- `./venv/bin/python -m unittest tests.test_cli.ForemanCLISmokeTests.test_waive_merge_creates_active_waiver -v`
- `./venv/bin/python -m unittest tests.test_supervisor_state.SupervisorStateTests.test_finalize_supervisor_merge_marks_task_done_and_completes_active_sprint tests.test_supervisor_state.SupervisorStateTests.test_finalize_supervisor_merge_prefers_explicit_task_id -v`
- `./venv/bin/python -m py_compile foreman/orchestrator.py foreman/cli.py foreman/dashboard_service.py scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py`
- `./venv/bin/foreman workflows && ./venv/bin/foreman roles`
- `./venv/bin/python -m unittest tests.test_runner.SignalParsingTests -v`
- `./venv/bin/python -m unittest tests.test_cli.ForemanCLISmokeTests.test_projects_command_reports_discovery_error_outside_repo tests.test_cli.ForemanCLISmokeTests.test_workflows_command_lists_shipped_workflows -v`
- `./venv/bin/python -m unittest tests.test_reviewed_codex -v`
- `./venv/bin/python -m unittest discover -s tests -v` — 500 tests passed in
  145.115 seconds.

Full unittest discovery emits pre-existing `ResourceWarning` output from
builtin test subprocess handling, but it now completes successfully in the
local repo venv.

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

- Sprint: `sprint-48-worker-fleet-minimax-smoke`
- Suggested branch: `feat/worker-fleet-minimax-smoke`
- Deliverable: a repeatable Claude Code/MiniMax M3 smoke that can delegate a
  narrow repo edit without hanging, plus the minimal role/env runner
  configuration needed to make Phase 1 model-fleet work reliable.
- After that: resume `sprint-47-active-run-lease-and-heartbeat-recovery` if it
  is still relevant.
