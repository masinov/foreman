# Current Sprint

- Active implementation sprint: `sprint-52-review-phases-6-7-supervision-transport`
  on `feat/supervision-and-transport` (top of the unmerged stack:
  `feat/meta-agent-persistence` → `feat/executor-overrides-ladder` →
  `feat/judge-and-tiered-review` → `feat/supervision-and-transport`).
- Branch: `feat/supervision-and-transport`.
- Last completed sprint: `sprint-47-active-run-lease-and-heartbeat-recovery`.
- Current deliverable: engine→manager supervision turns plus SSE/watch
  data_version polling, persisted retry counts, and the docs/ADR pass.

## Sprint 52 Review Phases 6 & 7 Supervision and Transport

Implemented on `feat/supervision-and-transport`:

1. `foreman/digest.py` `build_attention_digest` — compact supervision digest
   (trigger, affected task row, evidence verdict + failure reasons, last run
   detail, allowed responses; directed mode forbids mutation).
2. Orchestrator emits exactly one `engine.attention_needed` per block via
   `_create_system_run` (centralized) plus the `signal.blocker` path; loop
   limit is tagged `loop_limit`.
3. `POST /api/projects/{id}/meta/supervise` — builds the digest, runs one
   `origin="supervision"` meta turn, streams NDJSON; idempotent on the consumed
   `event_id` (409 on replay); validates the event is `engine.attention_needed`.
4. `process_message` gained `origin` and `consumed_event_id`; turns persist
   provenance; `ForemanStore.has_consumed_supervision_event` is the dedup guard.
5. `ForemanStore.data_version()` (PRAGMA) gates the SSE stream loop and the
   `foreman watch` loop so the expensive query only runs after another
   connection commits; poll interval lowered to 0.25s.
6. `Run.retry_count` is now written: `_execute_native_runner_step` counts
   `agent.infra_error` events and `_complete_run` persists the count.
7. Token-economy settings registered in `ProjectSettings` (`meta_agent_model`,
   `judge_*`, `review_diff_max_chars`); README multi-model/supervision section;
   ADR-0010.

Passing validation:

- `./venv/bin/python -m unittest tests.test_digest tests.test_settings -v`
- `./venv/bin/python -m unittest tests.test_dashboard.DashboardMetaAgentTests -v`
- `./venv/bin/python -m unittest tests.test_orchestrator.AgentSignalPersistenceTests -v`
- `./venv/bin/python -m unittest discover -s tests` (full suite — see PR doc)
- `./venv/bin/python scripts/validate_repo_memory.py`

## Sprint 51 Review Phases 4 & 5 Token Economy

## Sprint 51 Review Phases 4 & 5 Token Economy

Implemented on `feat/judge-and-tiered-review`:

1. `foreman/judge.py`: the keyword heuristic (`heuristic_checklist`,
   `_criterion_addressed`) is now the single owner; `judge_criteria` adds an
   opt-in cheap-model judge via a direct Anthropic-compatible `/v1/messages`
   HTTP call (settings `judge_base_url`, `judge_model`, `judge_api_key_env`,
   `judge_max_diff_chars`). Head/tail diff truncation; any HTTP/timeout/parse
   error falls back to the heuristic so evidence never crashes the workflow.
2. `build_completion_evidence` calls `judge_criteria` (new
   `_safe_branch_diff_content` helper for full `git diff`); maps the checklist
   into existing counts; records `CompletionEvidence.judged_by` (default
   "heuristic", keeps old evidence loadable) and emits it in the
   `engine.completion_evidence` event. Heuristic path is byte-identical.
3. New `escalate` outcome (`outcomes.py`, `_extract_decision_output`,
   `_VALID_OUTCOMES` for `triage_reviewer`/`frontier_reviewer`; reviewer
   normalization extended).
4. New roles `triage_reviewer` (cheap, all tools off) and `frontier_reviewer`
   (frontier, all tools off); both review a curated payload only.
5. `_build_prompt` adds `{completion_diff}` (capped `default_branch...branch`
   diff, `review_diff_max_chars` default 16000) populated only for
   `extract_decision` roles; added to `code_reviewer`, `security_reviewer`,
   and the two new roles.
6. New `workflows/development_tiered.toml`: develop → triage; triage
   approve→test, deny→develop, escalate→frontier review; review
   approve→test, deny/steer→develop; test/merge/done identical to
   `development` (including `completion:conflict`).

Passing validation:

- `./venv/bin/python -m unittest tests.test_judge -v` (10)
- `./venv/bin/python -m unittest tests.test_workflows tests.test_roles -v`
- `./venv/bin/python -m unittest tests.test_orchestrator.CompletionEvidenceTests -v`
- `./venv/bin/python -m unittest discover -s tests` (full suite — see PR doc)
- `./venv/bin/python scripts/validate_repo_memory.py`

## Sprint 50 Review Phase 3 Executor Overrides + Escalation Ladder

## Sprint 50 Review Phase 3 Executor Overrides + Escalation Ladder

Implemented on `feat/executor-overrides-ladder`:

1. Migration 12 adds `tasks.executor_overrides_json` and `tasks.complexity`,
   with additive schema-repair fallbacks. `Task` gains
   `executor_overrides: dict` and `complexity: str | None`; store row mapping
   and `save_task` updated.
2. Role `[agent]` gains optional `model_ladder` (`AgentConfig.model_ladder`);
   when present it supersedes `model` for tier selection.
3. `resolve_step_model` / `resolve_step_model_selection` (pure functions)
   implement the five-branch precedence: per-step override (ladder resumes
   above an override that appears in the ladder; otherwise pinned), role ladder
   indexed by `ladder_start + visit_count - 1` (ladder_start from override else
   a complexity map else 0), role `model`, project `default_model`, else None.
   Wired into the workflow loop and the native runner; a
   `workflow.model_selected` event records `{step, model, visit_count, source}`
   per agent step.
4. `signal.task_created` accepts and validates an optional `complexity`
   (`small|medium|large`) and persists it.
5. `foreman task add --complexity`; new `foreman task override TASK_ID
   [--step STEP=MODEL]... [--ladder-start N] [--clear]` (step ids validated
   against the project workflow); overrides/complexity shown in `task show`.
6. Dashboard `PATCH /api/tasks/{id}` accepts a validated full-object
   `executor_overrides`; task payloads expose `executor_overrides` and
   `complexity`.
7. `roles/developer_worker.toml` documents a commented `model_ladder` example
   and the per-role-per-endpoint limitation (no per-model env maps).

Passing validation:

- `./venv/bin/python -m unittest tests.test_orchestrator.ResolveStepModelTests -v`
- `./venv/bin/python -m unittest tests.test_orchestrator.ForemanOrchestratorTests.test_model_ladder_escalates_developer_model_across_repeated_visits -v`
- `./venv/bin/python -m unittest tests.test_cli.ForemanCLISmokeTests.test_task_override_round_trips_and_is_visible_in_show -v`
- `./venv/bin/python -m unittest tests.test_dashboard.DashboardSprintLifecycleTests.test_update_task_executor_overrides_validated_and_returned -v`
- `./venv/bin/python -m unittest discover -s tests` (full suite — see PR doc)
- `./venv/bin/python scripts/validate_repo_memory.py`

## Sprint 49 Review Phase 2 Manager Hardening

## Sprint 49 Review Phase 2 Manager Hardening

Implemented on `feat/meta-agent-persistence`:

1. Migration 11 adds `meta_sessions` and `meta_turns` plus
   `idx_meta_turns_project`; applies cleanly on fresh and existing DBs.
2. `ForemanStore` gains `get_meta_session`, `save_meta_session`,
   `append_meta_turn`, `list_meta_turns` (oldest-first with `has_more` cursor
   paging), and `clear_meta_session`.
3. `foreman/meta_agent.py` is now store-backed: the in-memory `_sessions`
   registry is gone, session id and history come from SQLite, the assistant
   turn is persisted in a `finally` path (flagged `interrupted` on
   error/cancel) so a crash never silently drops a turn, and `--model` is
   passed from the `meta_agent_model` project setting.
4. `build_state_header()` regenerates a compact, fixed-format world snapshot
   each turn (project/workflow/autonomy, sprint list with task counts, active
   sprint task table with 80-char blocked-reason truncation, pending decision
   gates, last 5 noteworthy events) with an explicit "trust this over your
   memory" disclaimer.
5. `build_operating_contract()` enumerates the manager's exact CLI surface and
   hard rules on the first turn of a session (re-injected after
   `clear_session`).
6. The dashboard `meta/history` endpoint supports `limit`/`before`/`has_more`;
   `meta/message` keeps the store open for the full streaming turn.
7. `foreman task add` gained `--description`, `--sprint SPRINT_ID`, and
   `--depends-on` (comma-separated, validated to exist in the same project).

Passing validation:

- `./venv/bin/python -m unittest tests.test_meta_agent -v` (7 new)
- `./venv/bin/python -m unittest tests.test_migrations -v`
- `./venv/bin/python -m unittest tests.test_cli.ForemanCLISmokeTests.test_task_add_targets_explicit_sprint_with_description_and_dependencies -v`
- `./venv/bin/python -m unittest tests.test_dashboard.DashboardMetaAgentTests -v`
- `./venv/bin/python -m unittest discover -s tests` — 528 tests passed
- `./venv/bin/python scripts/validate_repo_memory.py`
- `git diff --check`

## Sprint 47 Active-Run Lease Recovery

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
