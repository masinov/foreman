I checked `main`. The 25 items are partially implemented, but the implementation is not correct yet. There are several correctness regressions that will break autonomous mode, weaken lease safety, and leave the proof/event/settings work only partially wired.

I could not run the test suite locally because this environment cannot resolve `github.com` for cloning, and GitHub returned no CI statuses or workflow runs for the latest commit I checked. This review is based on direct repository inspection through the GitHub connector.

## Findings to fix

### 1. Autonomous mode is currently broken

`_task_started_received` is checked before the first developer step runs. For an orchestrator-created autonomous placeholder, the set is empty, so the workflow blocks before the developer ever has a chance to emit `signal.task_started`. The commit says “after first developer step,” but the code inserts the check before step execution. 

**Modify**

* `foreman/orchestrator.py`

  * Move the autonomous contract check to after the developer step completes.
  * Only enforce it after a `developer` run has returned.
  * Do not use only an in-memory `_task_started_received` set. Also accept persisted task fields:

    * title no longer placeholder
    * branch_name set
    * acceptance_criteria set
  * This avoids false blocking after orchestrator restart.

**Tests**

* Add/adjust `tests/test_orchestrator.py`.
* Passing conditions:

  * Autonomous placeholder reaches the developer step.
  * Developer emitting valid `signal.task_started` proceeds to review.
  * Developer not emitting `signal.task_started` blocks after the developer run, not before it.
  * Restarted orchestrator does not block a task whose persisted title/branch/criteria are already populated.
  * Invalid autonomous signal blocks with `workflow.autonomous_contract_missing`.

---

### 2. Lease uniqueness is not enforced by SQLite

The migration creates ordinary partial indexes on active leases, not a unique partial index. That means two active leases for the same `(project_id, resource_type, resource_id)` can exist if two connections race between “check existing” and “insert.” 

The store-side acquisition logic checks for an existing active lease and then inserts a new row, but without a unique database constraint this is not atomic across multiple SQLite connections. 

**Modify**

* `foreman/migrations.py`

  * Add a new migration:

    * `CREATE UNIQUE INDEX idx_leases_active_resource_unique ON leases(project_id, resource_type, resource_id) WHERE status = 'active';`
  * Keep the existing non-unique lookup index if useful.
* `foreman/store.py`

  * Change `acquire_lease(...)` to rely on the unique constraint.
  * Catch `sqlite3.IntegrityError` and return `None`.
  * Use `BEGIN IMMEDIATE` or a transaction pattern that prevents check/insert races.

**Tests**

* Extend `tests/test_leases.py`.
* Passing conditions:

  * Two separate `ForemanStore` connections cannot acquire the same active resource.
  * Concurrent acquire attempts result in exactly one active lease.
  * The losing acquire returns `None`, not an exception.
  * Released/expired resources can be reacquired.

---

### 3. Lease fencing is not implemented

`Lease.fencing_token` exists, but acquisition defaults to `1`, and reacquisition does not increment it. That defeats the point of fencing: a recovered worker cannot distinguish a stale holder from a newer holder.  

**Modify**

* `foreman/store.py`

  * In `acquire_lease(...)`, compute:

    * `next_fencing_token = MAX(fencing_token for same resource) + 1`
  * Do not accept an external `fencing_token` except maybe in tests.
* `foreman/orchestrator.py`

  * Include fencing token in internal runtime checks.
  * Do not trust stale in-memory lease tokens after reacquisition.

**Tests**

* Extend `tests/test_leases.py`.
* Passing conditions:

  * First lease has fencing token `1`.
  * Reacquired lease after expiry has fencing token `2`.
  * Reacquired lease after release has fencing token `2`.
  * Third acquisition increments again.
  * Old holder cannot renew after a newer fencing token exists.

---

### 4. Active-run recovery mishandles expired leases and leaks lease tokens

`_run_is_stale(...)` returns `False` whenever another holder has an active lease, but it does not first expire leases whose `expires_at` has passed. So an expired-but-still-`active` lease held by another holder can prevent recovery. 

The crash recovery event also persists the `lease_token` into the event payload. Lease tokens should be treated as secrets; context projection redacts them, but recovery events do not.  

**Modify**

* `foreman/orchestrator.py`

  * Before checking active lease ownership in `_run_is_stale(...)`, expire elapsed leases for that task.
  * Treat an expired active lease as recoverable.
  * Remove `lease_token` from `engine.crash_recovery` payload.
* `foreman/store.py`

  * Add a resource-scoped expiry helper:

    * `expire_resource_leases(project_id, resource_type, resource_id)`

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Running run with live lease held by another holder is not recovered.
  * Running run with expired lease held by another holder is recovered.
  * Recovery event includes lease ID, holder ID, fencing token.
  * Recovery event does not include lease token.

---

### 5. Branch invariant violations throw instead of being persisted as blocked workflow state

The branch invariant code raises `OrchestratorError` or `GitError` when the task branch is missing, the current branch is wrong, or the default branch changed. That does not reliably mark the task blocked, emit `engine.branch_violation`, or release the task lease. 

`events.py` defines an `engine_branch_violation(...)` constructor, but the branch-invariant code shown in the implementation does not use it. 

**Modify**

* `foreman/orchestrator.py`

  * Wrap branch pre/post checks.
  * On violation:

    * create a system run
    * emit `engine.branch_violation`
    * set task `blocked`
    * set `blocked_reason`
    * clear workflow resume state
    * release lease
    * return blocked task, not an uncaught exception
* `foreman/events.py`

  * Use the existing constructor or wire it properly.

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Missing task branch blocks task and emits `engine.branch_violation`.
  * Current branch mismatch blocks task and emits event.
  * Default branch mutation blocks task and emits event.
  * Lease is released after branch violation.
  * Orchestrator invocation returns cleanly with blocked task, not an uncaught exception.

---

### 6. Merge conflict handling regressed

`_merge(...)` now returns outcome `conflict` for merge conflicts. The shipped `development` workflow only transitions from `merge` on `success` and `failure`; there is no `completion:conflict` edge. That means conflicts now fall into fallback/blocking instead of carrying merge feedback back to the developer.  

**Modify one of these ways**

* Preferred:

  * `foreman/builtins.py`

    * Return outcome `failure` for merge conflicts, with conflict detail.
    * Keep `engine.merge_conflict` event.
* Or:

  * `workflows/development.toml`
  * `workflows/development_secure.toml`
  * `workflows/development_with_architect.toml`

    * Add `completion:conflict -> develop` with `carry_output = true`.

**Tests**

* Extend `tests/test_orchestrator.py`.
* Passing conditions:

  * Merge conflict returns to developer with carried output.
  * Developer receives conflict detail.
  * Work goes through review/test again after conflict resolution.
  * Task is not permanently blocked merely because a merge conflict occurred.

---

### 7. Completion guard does not actually gate on `proof_status`

The merge guard builds completion evidence, but `_completion_guard_block_reason(...)` only blocks implementation tasks when there are no changed files or when changes are docs/tests-only. It ignores `proof_status`, failed criteria, missing reviewer outcomes, missing security outcomes, and weak verdicts. If evidence construction returns `None`, merge proceeds. 

**Modify**

* `foreman/builtins.py`

  * In `_merge(...)`, require evidence to exist.
  * Require `evidence.proof_status == "passed"`.
  * Require no `failure_reasons`.
  * Require code review approval.
  * Require security review approval for `development_secure`.
  * If evidence is missing or failed, return `failure` or `blocked` consistently with workflow transitions.
* `foreman/orchestrator.py`

  * Build and persist evidence before merge.
  * Emit `engine.completion_evidence` for normal merge path, not only supervisor finalization.

**Tests**

* Extend `tests/test_orchestrator.py` and `tests/test_completion_evidence.py`.
* Passing conditions:

  * Evidence missing blocks merge.
  * `proof_status = failed` blocks merge.
  * Failed tests block merge.
  * Missing code review approval blocks merge.
  * Missing security approval blocks secure workflow merge.
  * Passed evidence allows merge.

---

### 8. Completion evidence is still incomplete

The `CompletionEvidence` model now has fields for reviewer and security outcomes, but the implementation explicitly initializes them empty and says they “can be wired in” later. That means the proof object is not yet tied to review truth. 

The criteria checklist is only `(criterion, addressed_bool)`, not `passed | failed | unknown` with evidence. Proof status is derived from score and tests, not from reviewer/security approval or full criteria status. 

**Modify**

* `foreman/orchestrator.py`

  * In `build_completion_evidence(...)`, derive:

    * latest code reviewer outcome
    * latest security reviewer outcome when present
    * test command and exit code
    * criteria checklist with status and evidence text
* `foreman/models.py`

  * Replace `criteria_checklist: tuple[tuple[str, bool], ...]` with structured dict/dataclass shape:

    * `criterion`
    * `status`
    * `evidence`
* `foreman/store.py`

  * Ensure structured checklist round-trips JSON.

**Tests**

* Extend `tests/test_completion_evidence.py`.
* Passing conditions:

  * Evidence includes `review_outcome = approve` after code review.
  * Secure workflow evidence includes `security_review_outcome = approve`.
  * Criteria can be `passed`, `failed`, or `unknown`.
  * Any failed/unknown required criterion prevents `proof_status = passed`.
  * Evidence round-trips through `completion_evidence_json`.

---

### 9. Event schema versioning exists but is not wired through the runtime

`foreman/events.py` defines versioned event constructors and `schema_version`, but runtime code still emits raw `BuiltinEventRecord` payloads directly in `builtins.py` without `schema_version`.  

**Modify**

* `foreman/orchestrator.py`

  * All `_emit_event(...)` calls should go through `foreman/events.py`.
* `foreman/builtins.py`

  * Replace raw payload dicts with event constructors.
* `foreman/runner/*`

  * Decide whether runner events get schema versioned at runner boundary or orchestrator persistence boundary.
* `foreman/events.py`

  * Add real validators for required fields, not only constructors.

**Tests**

* Extend `tests/test_events.py`.
* Add integration assertions in `tests/test_orchestrator.py`.
* Passing conditions:

  * Every persisted event emitted by a workflow has `schema_version`.
  * Invalid event payloads are rejected before save.
  * `engine.test_run`, `engine.merge`, `workflow.transition`, `agent.started`, and `signal.*` all persist versioned payloads.
  * Existing CLI history/watch still render events.

---

### 10. Settings validation is not wired into runtime paths

`foreman/settings.py` defines `ProjectSettings.from_raw(...)`, but runtime modules still read `project.settings` directly. For example, `executor.py` reads raw `project.settings` through `_int_setting`, `_float_setting`, `_string_setting`, and `_project_timeout_seconds`; `context.py` also reads raw `context_dir`.   

**Modify**

* `foreman/orchestrator.py`
* `foreman/executor.py`
* `foreman/builtins.py`
* `foreman/context.py`
* `foreman/cli.py`

Use `ProjectSettings.from_raw(project.settings)` at boundaries and fail early on invalid settings.

**Tests**

* Extend `tests/test_settings.py`, `tests/test_cli.py`, `tests/test_orchestrator.py`.
* Passing conditions:

  * Invalid `task_selection_mode` prevents run.
  * Negative limits are rejected.
  * Invalid CLI config assignment fails.
  * Valid defaults still initialize.
  * Runtime no longer directly depends on unvalidated setting values.

---

### 11. Workflow validation is too generic and allowed the merge-conflict bug

`WorkflowDefinition.validate()` allows a broad set of builtin outcomes, including `conflict`, but it does not validate role/builtin-specific emitted outcomes against actual shipped transitions. Because of this, `_builtin:merge` can emit `conflict` while shipped workflows do not route it. 

**Modify**

* `foreman/workflows.py`

  * Define role/builtin-specific outcome contracts:

    * `_builtin:merge`: `success`, `failure` or explicitly `conflict`
    * `_builtin:run_tests`: `success`, `failure`
    * `_builtin:mark_done`: `success`
    * `_builtin:human_gate`: `paused`
    * `code_reviewer`: `approve`, `deny`, `steer`
    * `security_reviewer`: `approve`, `deny`
    * `developer`: `done`, `blocked`, `error`
  * For every emitted non-terminal outcome, require a transition or intentional terminal/block declaration.
* `workflows/*.toml`

  * Add missing transitions or change emitted outcomes.

**Tests**

* Extend `tests/test_workflows.py`.
* Passing conditions:

  * Shipped workflows validate.
  * A merge step emitting `conflict` without a transition fails validation.
  * A reviewer step missing `deny` transition fails validation.
  * Mark-done with outgoing transition fails validation.
  * Unknown outcome fails validation.

---

### 12. Outcome normalization still admits unsafe ambiguity

`normalize_reviewer_decision(...)` accepts `yes`, `lgtm`, and `pass` as approval. That weakens the reviewer contract, which says reviewers must return exact decision strings. `normalize_agent_outcome(...)` also passes unknown outcomes through, leaving fallback behavior dependent on arbitrary model output. 

**Modify**

* `foreman/outcomes.py`

  * Make reviewer normalization strict:

    * only `APPROVE`, `DENY:`, `STEER:` or canonical lower-case internal equivalents.
  * Unknown agent outcomes should normalize to `error` or `blocked`, not pass through.
* `foreman/orchestrator.py`

  * Preserve raw output detail separately from canonical outcome.

**Tests**

* Extend `tests/test_outcomes.py`.
* Passing conditions:

  * `APPROVE` → `approve`.
  * `DENY: reason` → `deny`.
  * `STEER: action` → `steer`.
  * `LGTM`, `yes`, `pass` do not approve.
  * Unknown agent outcome causes block/fallback deterministically.

---

## Regression summary

The current main branch is not ready to delegate autonomous tightening work to itself. The most serious immediate regressions are:

1. Autonomous mode blocks before the developer can emit `task_started`.
2. Lease uniqueness is not enforced at the DB level.
3. Lease recovery can be blocked by expired active leases and logs lease tokens.
4. Branch violations can escape as exceptions instead of persisted blocked states.
5. Merge conflicts no longer route back to development.
6. Completion proof exists as data, but merge is not gated on `proof_status`.
7. Event schema versioning and settings validation are mostly present as modules, not consistently wired into runtime behavior.

Fix those before relying on Foreman to run its own development loop.
