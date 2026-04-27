Use this as the implementation order. Keep frontend untouched.

## 1. Add first-class leases

**Change**: introduce a real lease/claim system instead of using `Task.status = in_progress` and `Run.status = running` as soft locks. Current persisted entities are projects, sprints, tasks, runs, events, and decision gates, with no lease model/table. 

**Modify**

* `foreman/models.py`

  * Add `Lease` dataclass:

    * `id`
    * `project_id`
    * `resource_type`
    * `resource_id`
    * `holder_id`
    * `lease_token`
    * `fencing_token`
    * `status`: `active | released | expired`
    * `acquired_at`
    * `heartbeat_at`
    * `expires_at`
    * `released_at`
* `foreman/migrations.py`

  * Add migration for `leases`.
  * Add unique partial index on active resource lease:

    * one active lease per `(project_id, resource_type, resource_id)`.
* `foreman/store.py`

  * Add:

    * `acquire_lease(...)`
    * `renew_lease(...)`
    * `release_lease(...)`
    * `expire_leases(...)`
    * `get_active_lease(...)`
    * `list_leases(...)`
  * Acquisition must be atomic.
  * Expired leases must not block reacquisition.
* Create `foreman/leases.py`

  * Put lease token generation, expiry checks, and validation helpers here.

**Tests**

* Add `tests/test_leases.py`.
* Passing conditions:

  * A task can be leased once.
  * A second holder cannot lease the same active task.
  * The same holder can renew with the same token.
  * Wrong token cannot renew or release.
  * Expired lease can be reclaimed.
  * Released lease can be reclaimed.
  * Migration upgrades an existing DB without data loss.

## 2. Make task selection lease-aware

**Change**: task selection must atomically claim a task before returning it. This prevents two orchestrators from running the same task.

**Modify**

* `foreman/orchestrator.py`

  * Add orchestrator instance identity, for example `holder_id`.
  * `select_next_task(...)` should only return a task after successfully acquiring a task lease.
  * Directed mode must lease the selected `todo` or resumable `in_progress` task.
  * Autonomous mode must lease the placeholder task it creates.
  * `run_task(...)` must require a valid lease token.
  * Release the lease when the task reaches `done`, `cancelled`, or hard `blocked`.
  * Renew the lease between workflow steps.
* `foreman/store.py`

  * Add a transactional helper if needed:

    * `claim_next_directed_task(...)`
    * `claim_or_create_autonomous_task(...)`

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Two orchestrators cannot both execute the same `todo` task.
  * If one orchestrator leases a task, the second skips it.
  * Expired task lease allows recovery.
  * Lease is released after task reaches `done`.
  * Lease remains active while workflow is between developer/reviewer/test steps.

## 3. Make active run recovery lease-based

**Change**: stale running runs should be recovered only when the owning lease is expired or missing. Current behavior relies on “running run” recovery; it needs fencing to avoid killing live work.

**Modify**

* `foreman/orchestrator.py`

  * Change `_run_is_stale(...)` and `_recover_stale_running_runs(...)` to consult leases.
  * Add event payload fields:

    * `lease_id`
    * `holder_id`
    * `lease_token`
    * `fencing_token`
  * Recovery must mark old runs failed/timeout only after lease expiry.
* `foreman/store.py`

  * Add helpers to fetch active run lease by `run_id`.

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Live leased running run is not recovered.
  * Expired leased running run is recovered.
  * Recovery emits `engine.crash_recovery`.
  * Recovered task can be rerun by a new holder.
  * Fencing token increments on reacquisition.

## 4. Enforce branch invariants in the core runtime

**Change**: branch safety must be enforced by the orchestrator, not just by prompts. The developer prompt says “work only on the branch” and “never merge to main,” but that is not a hard runtime guarantee. 

**Modify**

* `foreman/git.py`

  * Add:

    * `head_sha(repo_path, ref)`
    * `branch_exists(repo_path, branch)`
    * `worktree_branch(repo_path)`
    * `assert_not_on_default_branch(...)`
    * `assert_default_branch_unchanged(...)`
* `foreman/orchestrator.py`

  * Before every agent step:

    * capture default branch HEAD.
    * verify task branch exists or is created.
    * verify current branch is task branch for directed mode.
  * After every agent step:

    * verify default branch HEAD did not change.
    * verify current branch is not default branch unless running merge builtin.
    * if violated, mark run failed and task blocked.
  * Emit `engine.branch_violation`.
* `foreman/builtins.py`

  * `_builtin:merge` is the only step allowed to move default branch.
  * Validate source branch and target branch before merge.

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Developer committing to main blocks task.
  * Developer changing default branch HEAD blocks task.
  * Merge builtin may change default branch.
  * Branch violation emits event and does not proceed to review.
  * Current branch is restored after successful task execution.

## 5. Make autonomous `task_started` mandatory

**Change**: autonomous mode should not proceed with an anonymous placeholder if the agent fails to declare title, branch, and acceptance criteria. The spec currently allows a degraded path; tighten it.

**Modify**

* `foreman/orchestrator.py`

  * In autonomous mode, after the first developer step, require task fields:

    * title not placeholder
    * branch_name set
    * acceptance_criteria set
    * task_type valid
  * If missing, block task with reason:

    * `Autonomous task did not emit required task_started signal.`
  * Emit `workflow.autonomous_contract_missing`.
* `foreman/runner/signals.py`

  * Keep parsing as-is, but add validation helpers:

    * `validate_task_started_payload(...)`
* `foreman/roles.py`

  * Update `SIGNAL_FORMAT_DOC` to mark `task_started` required in autonomous mode.

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Autonomous task with valid `signal.task_started` proceeds to review.
  * Missing signal blocks.
  * Missing branch blocks.
  * Missing criteria blocks.
  * Invalid task type blocks.
  * Blocked placeholder does not count as done.

## 6. Validate all structured signal payloads

**Change**: signals are currently parsed defensively but weakly typed. Add validation and explicit invalid-signal events.

**Modify**

* `foreman/runner/signals.py`

  * Add schema validation per signal type:

    * `task_started`: `title`, `branch`, `criteria`; optional `task_type`
    * `task_created`: `title`, `description`, `criteria`; optional `task_type`
    * `progress`: `message`
    * `blocker`: `message`
  * Invalid JSON should emit `signal.invalid` instead of silently disappearing.
  * Unknown signal type should emit `signal.unknown`.
* `foreman/orchestrator.py`

  * Handle `signal.invalid` and `signal.unknown` as persisted events.
  * For autonomous `task_started`, reject invalid payloads.
* `foreman/models.py`

  * No new model required.

**Tests**

* Extend or create `tests/test_signals.py`.
* Passing conditions:

  * Valid signals produce typed events.
  * Invalid JSON produces `signal.invalid`.
  * Unknown type produces `signal.unknown`.
  * Invalid `task_started` cannot update task.
  * Valid `task_created` creates a follow-up task in the active sprint.

## 7. Implement follow-up task creation from `signal.task_created`

**Change**: developer prompt tells agents to emit follow-up work, but the engine needs durable, validated task creation.

**Modify**

* `foreman/orchestrator.py`

  * When `signal.task_created` appears:

    * create a new `Task` in the active sprint.
    * set `created_by = "agent:<role_id>"`.
    * copy title, description, criteria, task type.
    * default status `todo`.
    * assign next `order_index`.
  * Emit `engine.task_created`.
* `foreman/store.py`

  * Add helper:

    * `next_task_order_index(sprint_id)`
* `foreman/roles.py`

  * Keep signal documentation aligned.

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Developer signal creates a durable task.
  * Created task belongs to active sprint.
  * Created task has `created_by = agent:developer`.
  * Invalid follow-up signal does not create a task.
  * Created task appears in board/history store queries.

## 8. Normalize workflow outcomes with typed constants

**Change**: outcomes are stringly typed across roles, workflows, runners, and builtins. Add a single normalization boundary.

**Modify**

* Create `foreman/outcomes.py`

  * Define canonical outcome constants:

    * `done`
    * `approve`
    * `deny`
    * `steer`
    * `success`
    * `failure`
    * `error`
    * `blocked`
    * `paused`
    * `killed`
  * Add `normalize_agent_outcome(...)`.
  * Add `normalize_reviewer_decision(...)`.
* `foreman/orchestrator.py`

  * Use outcome normalizer before transition lookup.
  * Malformed reviewer output should not be treated as approval.
* `foreman/executor.py`

  * Use canonical outcomes.
* `foreman/builtins.py`

  * Use canonical outcomes.
* `foreman/workflows.py`

  * Validate transition triggers reference known completion outcomes unless workflow opts out.

**Tests**

* Add `tests/test_outcomes.py`.
* Extend workflow loader tests if present.
* Passing conditions:

  * `APPROVE` normalizes to `approve`.
  * `DENY: reason` normalizes to `deny` with detail.
  * `STEER: action` normalizes to `steer` with detail.
  * Malformed reviewer output becomes `blocked` or `steer`, never `approve`.
  * Unknown workflow transition outcome blocks with fallback.

## 9. Fix test-result evidence extraction

**Change**: `_builtin:run_tests` emits `engine.test_run` with `exit_code`, but completion evidence should treat `exit_code == 0` as pass. Current evidence logic risks looking for a non-existent `passed` field.

**Modify**

* `foreman/orchestrator.py`

  * In `build_completion_evidence(...)`, compute:

    * `builtin_test_passed = payload["exit_code"] == 0`
    * `builtin_test_result = payload["command"]`
    * `builtin_test_detail = payload["output_tail"]`
  * Remove dependency on `engine.test_output` unless that event is actually emitted.
* `foreman/builtins.py`

  * Optionally add explicit `passed` field to `engine.test_run` payload for clarity.
* `tests/test_orchestrator.py`

  * Add evidence-specific assertions.

**Tests**

* Passing conditions:

  * Passing test command gives `builtin_test_passed = True`.
  * Failing test command gives `builtin_test_passed = False`.
  * Evidence stores command and output tail.
  * Evidence score includes test points only on exit code 0.
  * No test command gives failure evidence, not silent success.

## 10. Expand completion evidence into a real proof object

**Change**: completion evidence should be deterministic audit data, not mostly keyword/diff heuristics.

**Modify**

* `foreman/models.py`

  * Extend `CompletionEvidence` equivalent persisted shape if moved from orchestrator into models.
  * Add fields:

    * `base_sha`
    * `head_sha`
    * `merge_base_sha`
    * `commit_count`
    * `changed_files`
    * `test_command`
    * `test_exit_code`
    * `review_outcome`
    * `security_review_outcome`
    * `criteria_checklist`
    * `proof_status`: `pending | passed | failed`
    * `failure_reasons`
* `foreman/orchestrator.py`

  * Move `CompletionEvidence` dataclass to `models.py` or new `completion.py`.
  * Build evidence from:

    * task acceptance criteria
    * git commit range
    * changed files
    * latest review/security runs
    * latest test run
    * merge readiness
* `foreman/store.py`

  * Ensure `completion_evidence_json` can round-trip nested lists/dicts.
* Create `foreman/completion.py`

  * Put evidence construction/scoring/checklist logic here.

**Tests**

* Add `tests/test_completion_evidence.py`.
* Passing conditions:

  * Evidence contains base/head SHAs.
  * Evidence records test command and exit code.
  * Evidence records reviewer approval.
  * Evidence records security reviewer approval when secure workflow is used.
  * Evidence fails if no acceptance criteria exist unless task explicitly has a no-criteria override.
  * Evidence fails if no changed files and task type is not docs/spike/chore with explicit no-code rationale.

## 11. Make completion evidence gate merge

**Change**: merge should not occur merely because reviewer approved and tests passed once. Merge should require proof status passed.

**Modify**

* `foreman/orchestrator.py`

  * Before transition into `_builtin:merge`, build evidence.
  * If evidence fails, block task with `Completion evidence failed.`
  * Emit `engine.completion_evidence`.
  * Persist evidence before merge attempt.
* `foreman/builtins.py`

  * `_merge` should verify evidence is present and passed.
  * If missing/failed, return `failure`.
* `workflows/development.toml`

  * No new step required if enforced before merge.
  * Optionally add `_builtin:completion_gate` if a separate workflow step is preferred.
* `workflows/development_secure.toml`

  * Same behavior.

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Reviewer approve + tests pass + evidence pass → merge.
  * Reviewer approve + tests pass + evidence fail → block before merge.
  * Evidence failure emits event.
  * Task does not reach `done` without passed evidence.
  * Secure workflow requires both code and security review outcomes in evidence.

## 12. Add explicit event schema versions and validators

**Change**: events are the audit log. Payloads should be versioned and validated.

**Modify**

* Create `foreman/events.py`

  * Define event constructors:

    * `agent_started(...)`
    * `workflow_transition(...)`
    * `engine_test_run(...)`
    * etc.
  * Add `schema_version` to every payload.
  * Add validation for required keys.
* `foreman/orchestrator.py`

  * Replace raw `_emit_event(..., payload={...})` calls with event constructors.
* `foreman/builtins.py`

  * Return `BuiltinEventRecord` created through event helpers.
* `foreman/runner/base.py`

  * Ensure runner events include versioned payloads where possible.
* `foreman/store.py`

  * Store remains generic JSON, but invalid events should be rejected before save.

**Tests**

* Add `tests/test_events.py`.
* Passing conditions:

  * Known events include `schema_version`.
  * Missing required payload keys raises an error in tests.
  * Old event listing still works.
  * CLI history/board/watch still render versioned events.
  * Invalid event cannot be saved through orchestrator helpers.

## 13. Enforce task-level and sprint-level cost gates

**Change**: run-level cost/time gates exist in runners, but task/sprint gates from the spec should be enforced by the orchestrator.

**Modify**

* `foreman/orchestrator.py`

  * Before each workflow step:

    * sum task run cost.
    * compare `cost_limit_per_task_usd`.
    * sum sprint run cost.
    * compare `cost_limit_per_sprint_usd`.
  * Block task or sprint according to setting.
  * Emit:

    * `gate.cost_exceeded`
    * `gate.time_exceeded`
* `foreman/store.py`

  * Ensure `run_totals(...)` supports task, sprint, project scopes efficiently.
* `foreman/runner/codex.py`

  * Keep USD zero if unavailable, but include a clear event/field:

    * `cost_unavailable = true`.
* `foreman/cli.py`

  * Cost output already warns about zero-cost token runs; preserve that behavior. 

**Tests**

* Extend `tests/test_orchestrator.py` and `tests/test_cli.py`.
* Passing conditions:

  * Task blocks when cumulative cost exceeds task limit.
  * Sprint blocks or stops when sprint cost exceeds sprint limit.
  * Cost-exceeded event includes limit, actual, and scope.
  * Codex token usage with zero USD does not fake a cost.
  * CLI cost shows warning for token runs with zero cost.

## 14. Enforce max step visits before executing the step

**Change**: loop limits must be strict and auditable. The spec describes `max_step_visits`; tests show visit counts are already tracked, but tighten enforcement.

**Modify**

* `foreman/orchestrator.py`

  * Increment visit count before step execution.
  * If count exceeds `max_step_visits`, block immediately.
  * Persist task visit counts before returning.
  * Emit `workflow.loop_limit`.
* `foreman/store.py`

  * Ensure `step_visit_counts` round-trips correctly.
* `foreman/cli.py`

  * Board/history already renders visit counts; keep compatible. 

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Repeated review denial eventually blocks.
  * Repeated test failure eventually blocks.
  * Block reason includes step and limit.
  * No extra agent run is created after limit is exceeded.
  * Visit counts persist after reload.

## 15. Make reviewer/security roles truly read-only

**Change**: reviewer TOML disallows Bash/write/edit tools, but runtime should verify this maps correctly across Claude and Codex.

**Modify**

* `roles/code_reviewer.toml`

  * Keep disallowed tools explicit.
  * Consider `permission_mode = "readOnly"` if supported by runner contract.
* `roles/security_reviewer.toml`

  * Same.
* `foreman/runner/claude_code.py`

  * Verify disallowed tools are always passed.
  * Add read-only permission mode mapping if supported.
* `foreman/runner/codex.py`

  * Ensure command/file-change approval requests are denied when disallowed.
  * Ensure sandbox resolves to read-only for reviewer roles.
* `foreman/orchestrator.py`

  * Emit `engine.role_policy` at run start with backend, permission mode, disallowed tools.

**Tests**

* Extend runner tests or add:

  * `tests/test_runner_policy.py`
* Passing conditions:

  * Claude reviewer command contains disallowed tools.
  * Codex reviewer command/file approval returns decline/cancel.
  * Developer can write when allowed.
  * Reviewer cannot write even if model requests it.
  * Security reviewer cannot run Bash.

## 16. Persist human-gate decisions as first-class records

**Change**: human gates currently persist task resume state and events. Add durable decision records for auditability.

**Modify**

* `foreman/models.py`

  * Add `HumanGateDecision` dataclass:

    * `id`
    * `project_id`
    * `task_id`
    * `workflow_step`
    * `decision`
    * `note`
    * `decided_by`
    * `decided_at`
    * `run_id`
* `foreman/migrations.py`

  * Add `human_gate_decisions` table.
* `foreman/store.py`

  * Add save/list/get helpers.
* `foreman/orchestrator.py`

  * In `resume_human_gate(...)`, persist decision before resuming.
  * Link decision to the synthetic run/event.
* `foreman/cli.py`

  * `approve`/`deny` output should include decision ID if those handlers are present lower in file.

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Approve creates decision row.
  * Deny creates decision row with note.
  * Decision row links to task and workflow step.
  * Resume emits event and persists decision.
  * Duplicate decision on non-blocked task is rejected.

## 17. Validate workflow definitions against role/builtin outcome contracts

**Change**: workflow loader validates step references, but should also validate transitions against known role outputs and builtins.

**Modify**

* `foreman/workflows.py`

  * Add optional validation:

    * builtin role supports listed outcomes.
    * reviewer role transitions include only valid reviewer outcomes.
    * terminal `mark_done` has no outgoing transition.
    * every non-terminal step has at least one outgoing transition.
* `foreman/roles.py`

  * Add `completion.output` metadata enough to infer role output type:

    * decision
    * summary
    * json
    * builtin
* `workflows/*.toml`

  * Fix any invalid transition discovered by stricter validation.

**Tests**

* Add or extend `tests/test_workflows.py`.
* Passing conditions:

  * Shipped workflows load.
  * Unknown role fails.
  * Unknown transition target fails.
  * Duplicate transition fails.
  * Invalid completion outcome fails.
  * Terminal done step without outgoing transition is accepted.

## 18. Split completion proof from supervisor-finalize path

**Change**: `finalize_supervisor_merge(...)` exists to sync state after external supervised script merges. Product runtime should not rely on external supervisor merge state.

**Modify**

* `foreman/orchestrator.py`

  * Keep `finalize_supervisor_merge(...)` only for compatibility.
  * Move evidence construction into normal workflow before `_builtin:merge`.
  * Ensure `_builtin:mark_done` is the only normal path to `done`.
* `foreman/supervisor_state.py`

  * Ensure it calls the compatibility path only.
  * Mark as compatibility/legacy if appropriate.
* `scripts/reviewed_claude.py`

  * Replace custom merge-state behavior with call into product orchestrator compatibility layer, or clearly mark script bootstrap-only.
* `scripts/reviewed_codex.py`

  * Same.

**Tests**

* Extend `tests/test_orchestrator.py`.
* Add script-level test only if scripts are kept product-supported.
* Passing conditions:

  * Normal orchestrator run produces evidence before merge.
  * External finalize still maps branch to task and marks done.
  * External finalize cannot mark wrong project/task done.
  * External finalize emits compatibility event.
  * No duplicate completion evidence is created.

## 19. Make bootstrap scripts non-authoritative

**Change**: the repo currently has both product orchestrator and older reviewed scripts. The architecture says scripts are bootstrap tooling, not product architecture. 

**Modify**

* `scripts/reviewed_claude.py`

  * Add top-level warning in docstring and terminal output:

    * “bootstrap-only; not product runtime.”
  * Remove any behavior that conflicts with `ForemanOrchestrator`, especially direct state assumptions.
* `scripts/reviewed_codex.py`

  * Same.
* `README.md`

  * Clarify that `foreman run`/orchestrator is authoritative.
  * Keep scripts documented only as legacy bootstrap tools.
* `docs/ARCHITECTURE.md`

  * Clarify deprecation path.

**Tests**

* Existing script py_compile validation must pass.
* Passing conditions:

  * `python -m py_compile scripts/reviewed_claude.py`
  * `python -m py_compile scripts/reviewed_codex.py`
  * README and architecture no longer imply scripts are primary runtime.
  * No product tests require scripts for normal workflow completion.

## 20. Make project settings validation explicit

**Change**: settings are currently JSON blobs. Add validation so bad project settings do not produce hidden runtime behavior.

**Modify**

* Create `foreman/settings.py`

  * Define `ProjectSettings` parser/validator.
  * Validate:

    * `task_selection_mode`
    * `max_autonomous_tasks`
    * `max_step_visits`
    * `test_command`
    * `time_limit_per_run_minutes`
    * `cost_limit_per_task_usd`
    * `cost_limit_per_sprint_usd`
    * `event_retention_days`
    * `context_dir`
* `foreman/scaffold.py`

  * Use settings defaults from `settings.py`.
* `foreman/orchestrator.py`

  * Replace raw `project.settings.get(...)` calls with validated settings object.
* `foreman/cli.py`

  * Config assignment should validate on write.

**Tests**

* Add `tests/test_settings.py`.
* Extend CLI tests.
* Passing conditions:

  * Valid defaults parse.
  * Invalid task selection mode fails.
  * Negative max visits fails.
  * Empty test command is allowed only when explicitly configured and causes test step failure.
  * CLI rejects invalid config assignment.

## 21. Strengthen context projection for autonomous work

**Change**: `.foreman/` context should include the current lease/proof/workflow state so agents can self-correct without relying only on prompt text.

**Modify**

* `foreman/context.py`

  * Include:

    * current task ID/title/status
    * branch
    * acceptance criteria
    * current workflow step
    * carried feedback
    * lease holder/expiry, without secret token
    * recent review/test failure summary
    * required autonomous signal contract
* `foreman/orchestrator.py`

  * Ensure context projection is written:

    * before every agent step
    * after every step
    * after block/done
* `foreman/builtins.py`

  * Keep `_builtin:context_write` compatible.

**Tests**

* Extend context tests if present, otherwise add `tests/test_context.py`.
* Passing conditions:

  * Context file exists before agent run.
  * Context includes current step and carried output.
  * Context excludes lease token.
  * Context includes autonomous signal requirements.
  * Context updates after reviewer denial/test failure.

## 22. Add run-attempt/failure classification

**Change**: distinguish model failure, infrastructure failure, preflight failure, policy violation, timeout, killed, test failure, and workflow fallback.

**Modify**

* `foreman/models.py`

  * Add optional `failure_type` to `Run`, or encode in `outcome_detail` plus event.
* `foreman/migrations.py`

  * Add `runs.failure_type` if using column.
* `foreman/runner/base.py`

  * Keep `PreflightError` non-retryable.
  * Add normalized event payload:

    * `failure_type`
* `foreman/orchestrator.py`

  * Map failures:

    * preflight → `preflight`
    * infrastructure exhausted → `infrastructure`
    * policy/branch violation → `policy`
    * gate killed → `gate`
    * workflow fallback → `workflow`
* `foreman/cli.py`

  * History should display failure type if present.

**Tests**

* Extend `tests/test_orchestrator.py` and runner tests.
* Passing conditions:

  * Preflight failure creates one failed run and no retry.
  * Infrastructure error retries configured number.
  * Branch violation records `policy`.
  * Gate kill records `gate`.
  * CLI history prints failure type.

## 23. Add full merge preflight

**Change**: merge should validate repository state before attempting merge.

**Modify**

* `foreman/git.py`

  * Add merge preflight:

    * source branch exists
    * target branch exists
    * worktree clean
    * target branch currently checkout-able
    * source branch is not target branch
    * source contains commits ahead of target
* `foreman/builtins.py`

  * `_merge` must call preflight.
  * Return structured failure detail on preflight failure.
* `foreman/orchestrator.py`

  * Carry merge failure detail back to developer.

**Tests**

* Extend `tests/test_orchestrator.py` or add `tests/test_git.py`.
* Passing conditions:

  * Missing branch fails before merge.
  * Dirty worktree fails before merge.
  * Source equals target fails.
  * No commits ahead fails unless task type allows no-code merge.
  * Merge conflict returns failure and loops back to develop.

## 24. Add acceptance-criteria checklist artifact

**Change**: acceptance criteria should become a checklist the developer/reviewer/proof gate can reason about.

**Modify**

* `foreman/models.py`

  * Optionally add `Task.acceptance_checklist_json`, or keep inside completion evidence.
* `foreman/completion.py`

  * Parse acceptance criteria into checklist items.
  * Record per item:

    * `text`
    * `status`: `passed | failed | unknown`
    * `evidence`
* `roles/developer.toml`

  * Ask developer to explicitly address each criterion.
* `roles/code_reviewer.toml`

  * Ask reviewer to verify each criterion explicitly.
* `foreman/orchestrator.py`

  * Include checklist in reviewer prompt context and completion evidence.

**Tests**

* Extend `tests/test_completion_evidence.py`.
* Passing conditions:

  * Multiline criteria parse into separate checklist items.
  * Developer summary can be associated with checklist.
  * Reviewer denial marks failed/unknown criteria.
  * Merge gate fails if any required item is failed/unknown.
  * Checklist persists in `completion_evidence_json`.

## 25. Update docs only after code behavior exists

**Change**: align docs with the tightened runtime after implementing the code changes above.

**Modify**

* `docs/specs/engine-design-v3.md`

  * Replace degraded autonomous placeholder behavior with mandatory autonomous contract.
  * Add leases.
  * Add completion proof gate.
  * Add event schema versioning.
* `docs/ARCHITECTURE.md`

  * Record leases, proof gate, branch enforcement, and script deprecation.
* `README.md`

  * Update current state and validation commands.
* `AGENTS.md`

  * Add instructions for future agents:

    * use orchestrator as source of truth
    * do not reintroduce script-only behavior
    * preserve lease/proof invariants

**Tests**

* Passing conditions:

  * Documentation references implemented files/commands only.
  * No doc claims a feature that tests do not cover.
  * `scripts/validate_repo_memory.py` passes if still required.
  * Existing README validation commands remain accurate.

## Final validation command set

The delegated agent should finish with these passing:

```bash
./venv/bin/python -m unittest discover -s tests -v
./venv/bin/python -m py_compile foreman/*.py
./venv/bin/python -m py_compile foreman/runner/*.py
./venv/bin/python -m py_compile scripts/reviewed_claude.py
./venv/bin/python -m py_compile scripts/reviewed_codex.py
./venv/bin/foreman --help
./venv/bin/foreman projects --help
./venv/bin/foreman board --help
./venv/bin/foreman history --help
./venv/bin/foreman cost --help
./venv/bin/foreman watch --help
```

The minimum backend correctness target after this sequence: one orchestrator cannot duplicate another’s work, autonomous tasks cannot proceed without a declared contract, default-branch mutations are blocked except by merge, reviewer/test/proof gates are mandatory before merge, and every decision needed to trust a task completion is persisted in SQLite.
