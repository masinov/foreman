# Current Sprint

- Active implementation sprint: none; `sprint-47-active-run-lease-and-heartbeat-recovery`
  is merged.
- Branch: none for implementation work; docs closeout branch is
  `docs/active-run-lease-closeout`.
- Local Foreman sprint: `sprint-review-phase-0-correctness` in `.foreman.db`
- Last completed sprint: `sprint-48-worker-fleet-minimax-smoke`
- Current deliverable: harden task lease liveness during native runner streams
  and crash recovery.

## Sprint 47 Active-Run Lease Recovery

Implemented on `feat/active-run-lease-heartbeat-recovery` and merged to
`main` at `5fbfc26`:

1. Added in-step native runner lease heartbeats so long Claude/Codex streams
   renew the task lease before the workflow step returns.
2. Added stale active-lease liveness checks based on task lease heartbeat age.
3. Added forced resource-lease expiry for recovered stale runs so reset tasks
   can be reacquired immediately.
4. Added regression coverage for forced lease expiry, crash-recovery token
   redaction, live-holder protection, and native stream heartbeat behavior.
5. Used MiniMax M3 through Claude Code for the bulk implementation and test
   drafting; final review, cleanup, docs, and validation are supervised here.

Passing validation:

- `./venv/bin/python -m unittest tests.test_orchestrator -v`
- `./venv/bin/python -m unittest tests.test_leases -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `git diff --check`
- `./venv/bin/python -m unittest discover -s tests -v` - 518 tests passed

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

## Sprint 48 Outcome

- Sprint: `sprint-48-worker-fleet-minimax-smoke`
- Branch: `feat/worker-fleet-minimax-smoke`
- Merged to `main`: `07649e6`
- Deliverable: repeatable Claude Code/MiniMax M3 smoke plus the minimal
  role/env runner configuration needed to make Phase 1 model-endpoint work
  reliable.
- Next: resume `sprint-47-active-run-lease-and-heartbeat-recovery` if it is
  still relevant.

## Sprint 48 Progress

Implemented on `feat/worker-fleet-minimax-smoke`:

1. Added `AgentRunConfig.env` and per-role `[agent.env]` loading.
2. Added `foreman.runner.env.resolve_env()` with literal, `env:NAME`,
   `env:NAME?fallback`, missing-required, and `_DIR` or `_PATH` expansion
   behavior.
3. Wired Claude Code and Codex runners to pass merged process environment only
   when role env is configured.
4. Wired the orchestrator to resolve role env before native execution; missing
   required env vars produce one preflight-style `agent.error` and consume no
   runner retries.
5. Added `roles/developer_worker.toml` as the sequential worker-model role
   example with commented MiniMax settings and isolated `CLAUDE_CONFIG_DIR`.
6. Documented the working MiniMax CLI smoke and the no-worker-pool boundary.

Manual MiniMax result:

- Sandbox-local MiniMax smoke reached Claude CLI API retries and timed out with
  `apiKeySource: none`, so the sandbox did not see the normal host-side
  Claude/MiniMax configuration.
- Escalated host-side smoke passed:
  `timeout 90 claude --print --model minimax-m3 "Reply with exactly: minimax-ok"`.
- Escalated host-side edit smoke passed with
  `--permission-mode bypassPermissions`: MiniMax M3 used Claude Code `Write`,
  created `/tmp/foreman-minimax-smoke/minimax_smoke.txt`, and returned
  `TASK_COMPLETE`.

Passing focused validation:

- `./venv/bin/python -m unittest tests.test_runner_env tests.test_roles tests.test_runner tests.test_runner_claude tests.test_runner_codex -v`
- `./venv/bin/python -m unittest tests.test_orchestrator.ForemanOrchestratorTests.test_native_runner_resolves_role_env_before_execution tests.test_orchestrator.ForemanOrchestratorTests.test_missing_required_role_env_fails_once_without_runner_retry tests.test_cli.ForemanCLISmokeTests.test_roles_command_lists_shipped_roles -v`
- `./venv/bin/python -m unittest discover -s tests -v` — 513 tests passed in
  148.910 seconds.
