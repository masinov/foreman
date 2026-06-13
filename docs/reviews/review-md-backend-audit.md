# Backend audit — `docs/specs/review.md` implementation

Date: 2026-06-13
Auditor: Claude (Opus 4.8), independent read-through
Scope: backend only (`foreman/`, `roles/`, `workflows/`, migrations, CLI).
Frontend explicitly out of scope.
Method: read `review.md` phase-by-phase, traced each item to source, ran the
full suite (`571 tests, OK`).

## Verdict

**The review spec is implemented end-to-end and the backend is functional.**
All seven phases (0–7) are present and wired, the full test suite is green, and
the acceptance criteria stated in the spec are met. I found **one genuine
functional gap** (partial Phase 6 trigger wiring) and a couple of cosmetic
deviations, none of which break the harness. Details below.

---

## Phase-by-phase verification

### Phase 0 — Correctness fixes — ✅ complete

| Item | Status | Evidence |
|------|--------|----------|
| 0.1 `UnboundLocalError` on first native step (`engine.role_policy` after `run` exists) | ✅ | role-policy emission now after `_create_running_run`; covered by `AgentSignalPersistenceTests` |
| 0.2 `signal.task_created` `NameError` (`_apply_agent_signal(run, ...)`) | ✅ | `orchestrator.py:2870–2917` takes `run`, emits `engine.task_created` against it |
| 0.3 missing `uuid4` import in CLI | ✅ | imported; `foreman waive-merge` CLI test passes |
| 0.4 merge conflicts take `completion:conflict` | ✅ | `outcomes.py` `CONFLICT` in `CANONICAL_OUTCOMES`, `normalize_agent_outcome` passes it through; `development_tiered` keeps the `completion:conflict` edge |
| 0.5 FK violation on run-less human events | ✅ | `DashboardService._ensure_event_run` used in `create_human_message`, `stop_agent`, `stop_task`, `update_task_fields`; latest run used |
| 0.6 dashboard process registry across requests | ✅ | module-level `_RUNNING_PROCS` + `_RUNNING_PROCS_LOCK`; `stop_agent` terminates the subprocess; `agent_running` in payloads |
| 0.7 evidence rebuilt every prompt | ✅ | gated on `role.completion.output.extract_decision`; `_completion_evidence_stale` invalidates on branch-head move |
| 0.8 `cancel_task` stale workflow state | ✅ | `cancel_task` clears `workflow_current_step`/carried output, sets `completed_at` |
| 0.9 remove dead `executor.py` | ✅ | `foreman/executor.py` and `tests/test_executor.py` gone; `AgentExecutor` protocol retained |

### Phase 1 — Multi-model fleet via env injection — ✅ complete

- `AgentConfig.env` + `roles.py` parsing; `runner/env.py` `resolve_env`
  implements literal / `env:NAME` / `env:NAME?fallback` / `_DIR`/`_PATH`
  expansion, raising `PreflightError` on missing required vars.
- `AgentRunConfig.env`; both runners pass `{**os.environ, **config.env}` to
  `Popen` **only when `config.env` is non-empty** (`claude_code.py:72`,
  `codex.py:332`).
- `_execute_native_runner_step` calls `resolve_env(role.agent.env)`; failures
  surface on the preflight path (one failed run, no infra retries).
- 1.4: `run_totals` includes `zero_cost_token_runs`, and the whole `totals`
  dict is embedded in `get_project`/`get_sprint`/`list_projects` payloads — so
  it is exposed as required.
- `roles/developer_worker.toml` shipped with the commented Minimax example.
- Tests: `test_runner_env.py`, env-merge runner tests, preflight orchestrator
  test.

### Phase 2 — Manager hardening — ✅ complete

- Migration 11 (`meta_sessions`, `meta_turns` with the `role IN (…, 'system')`
  CHECK and the project/created_at index).
- `meta_agent.process_message` is store-backed, drops the in-memory registry,
  persists the user turn first and the assistant turn in `finally` (flagged
  `interrupted` on crash), and passes `--model` from `meta_agent_model`.
- `build_state_header` / operating contract; `meta/history` supports
  `limit`/`before`/`has_more`.
- CLI: `task add --description --sprint --depends-on` (deps validated in-project).
- Tests: `test_meta_agent.py`, migration + dashboard history tests.

### Phase 3 — Executor overrides + escalation ladder — ✅ complete

- Migration 12 (`executor_overrides_json`, `complexity`); `Task` fields +
  `validate_executor_overrides`.
- `AgentConfig.model_ladder`; `resolve_step_model_selection` implements the full
  five-branch precedence including the **override-in-ladder resume** case
  (`orchestrator.py:3096`). Emits `workflow.model_selected` with `source`.
- Wired into the workflow loop (`:1579`) and native runner (`:2569`).
- `signal.task_created` validates/persists `complexity`; `task add --complexity`.
- `foreman task override` CLI; `executor_overrides` in `PATCH /api/tasks/{id}`
  and in `get_task`/`list_sprint_tasks` payloads.

### Phase 4 — LLM-judged criteria — ✅ complete

- `judge.py`: heuristic is the single owner (`heuristic_checklist`,
  `_criterion_addressed`); `judge_criteria` is opt-in (`/v1/messages`, head/tail
  `truncate_diff`, fence-stripping parse, **falls back to heuristic on any
  error**).
- `build_completion_evidence` calls it via `_safe_branch_diff_content`, maps
  passed→`criteria_addressed`, partial→`criteria_partially_addressed`, records
  `CompletionEvidence.judged_by`, and emits it in `engine.completion_evidence`.
- Heuristic path byte-identical (regression-tested).

### Phase 5 — Tiered review — ✅ complete

- `ESCALATE` outcome; `_extract_decision_output` recognizes `ESCALATE` and
  `ESCALATE: <reason>` (`:3310`).
- `triage_reviewer` / `frontier_reviewer` roles; `_VALID_OUTCOMES` extended.
- `_build_prompt` `completion_diff` capped by `review_diff_max_chars`, populated
  **only** for `extract_decision` roles.
- `workflows/development_tiered.toml` with `triage --completion:escalate--> review`.

### Phase 6 — Supervision turns — ⚠️ complete with one gap (see below)

- `digest.py build_attention_digest`; `_create_system_run` centralizes the
  single `engine.attention_needed` emission on every blocked system run;
  `signal.blocker` and `loop_limit` paths tagged.
- `POST /meta/supervise`: validates the event is `engine.attention_needed`,
  409 on a replayed `event_id` (`has_consumed_supervision_event`), runs one
  `origin="supervision"` turn from the digest; directed-mode no-mutation
  instruction is baked into the digest.

### Phase 7 — Transport polish — ✅ complete

- `ForemanStore.data_version()` gates both the SSE stream loop
  (`dashboard_backend.py:286`, heartbeat preserved) and `foreman watch`
  (`cli.py:1010`); `STREAM_POLL_INTERVAL_SECONDS = 0.25`.
- `Run.retry_count` counted from `agent.infra_error` events and persisted in
  `_complete_run`.
- README multi-model/supervision section; ADRs (see deviation note).

---

## Findings

### G1 — RESOLVED (2026-06-13, branch `feat/supervision-triggers-and-docs`)

The two missing triggers are now emitted: `evidence_failed` fires when a
builtin completion/merge guard blocks with `proof_status == "failed"` (selected
by `_attention_trigger_for_block`), and `sprint_resolved` fires from
`_advance_sprint` whenever the engine stops at a sprint boundary
(supervised/directed handoff or no further work) via `_emit_sprint_attention`.
Regression tests:
`CompletionGuardTests.test_merge_guard_block_emits_evidence_failed_attention`,
`test_attention_trigger_for_block_selects_by_proof_status`, and
`SprintAdvancementTests.test_{supervised_sprint_completion,directed_idle}_emits_sprint_resolved*`
/ `test_autonomous_auto_advance_does_not_emit_sprint_resolved`. Full suite 577
passing. Original finding retained below for context.

### G1 (minor, functional) — two supervision triggers are defined but never emitted

`digest.py` labels four triggers — `task_blocked`, `evidence_failed`,
`loop_limit`, `sprint_resolved` — but the orchestrator only ever emits
`engine.attention_needed` with `task_blocked` (default in `_create_system_run`,
plus `signal.blocker`) and `loop_limit`.

- **`evidence_failed`** is never raised. Spec §6.2 says to emit attention "or
  [when] `proof_status` lands `failed` at a guard." Today a weak-evidence
  outcome routes through the review/deny loop rather than blocking, so the
  manager is not proactively pinged on a proof-gate failure that does not also
  block the task.
- **`sprint_resolved`** is never raised. `_advance_sprint` emits
  `engine.sprint_completed` / `engine.sprint_ready` but no
  `engine.attention_needed`, so finishing a sprint does not wake the manager.

**Impact:** low. The digest builder and `/meta/supervise` endpoint already
handle both triggers correctly, so this is purely a matter of adding two
emission sites. The Phase 6 acceptance criteria (which only test the blocking
path) still pass. The autonomous supervision thread is simply less proactive
than the spec's full taxonomy implies.

**Suggested fix (small, ~1 slice):** emit `engine.attention_needed` with
`trigger="sprint_resolved"` in `_advance_sprint` when autonomy is
`supervised`/`directed` (i.e., where a human/manager confirmation is wanted),
and with `trigger="evidence_failed"` at the proof gate when `proof_status`
becomes `failed` without an accompanying block. Both reuse `_emit_attention_needed`.

### G2 (cosmetic) — ADR numbering differs from the spec

Spec §7.3 names `ADR-0006-multi-model-fleet-via-env-injection.md` and
`ADR-0007-tiered-review-and-llm-judged-evidence.md`. Those numbers were already
taken (`ADR-0006-sprint-autonomy-levels`, `ADR-0007-sprint-planner-chat-session`),
so the implementation correctly landed the same decisions as
`ADR-0009-multi-model-endpoints-via-role-env.md` and
`ADR-0010-tiered-review-and-llm-judged-evidence.md`. Content is captured; only
the numbers differ. No action needed beyond noting it.

### G3 (note, not a gap) — heuristic uses status `"unknown"`, judge uses `"failed"`

`heuristic_checklist` emits `passed | partial | unknown`; the LLM judge emits
`passed | partial | failed`. Downstream counting only keys on `passed` and
`partial`, so the two are equivalent for `proof_status` derivation. Intentional
(keeps the pre-existing heuristic output byte-identical). No action needed.

---

## Validation run for this audit

- `./venv/bin/python -m unittest discover -s tests` → **Ran 571 tests … OK**
  (187s).
- Source traced for every phase item listed above.

## Bottom line

The backend faithfully implements `review.md` and is feature-complete for
backend purposes. **G1 (the supervision-trigger gap) has since been closed** and
a full operator manual lives at `docs/MANUAL.md`. No outstanding gaps remain in
the review-roadmap scope; the only open items are the deferred Tier-3 SSE
pub/sub redesign and the frontier-`STEER` re-review escape hatch, both already
in the backlog.
