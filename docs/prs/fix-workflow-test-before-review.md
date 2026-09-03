# PR Summary: fix/workflow-test-before-review

## Summary

Sprint 53, slice 4. Every shipped workflow now runs the test built-in before
any review, so reviewers judge with real test results in the engine
evidence, and every workflow ends in a `merge_approval` human gate whose
policy decides whether a person must authorize the merge or the engine may
approve it on its own with an audit record. This is the first piece of the
autonomy-as-policy design from the readiness review.

## Scope

- **Workflow order.** `development`, `development_secure`,
  `development_tiered`, and `development_with_architect` are
  `develop → test → <reviews> → merge_approval → merge → done`. A test
  failure returns straight to develop with the output carried; review denial
  and steer behave as before. The secure workflow also gained the time gate
  the others already had.
- **Gate policy on steps.** `WorkflowStep.policy` (TOML `policy = ...`) names
  the project setting that governs a `_builtin:human_gate` step. Only
  `merge_approval` and `plan_approval` are valid, and only on gate steps.
- **Settings.** `merge_approval` (default `auto`) and `plan_approval`
  (default `human`), each `auto` or `human`, validated by `ProjectSettings`.
- **Per-task exception.** `executor_overrides.gates` maps a policy to `auto`
  or `human` for one task and takes precedence over the project setting;
  validated by `validate_executor_overrides`, so the dashboard `PATCH
  /api/tasks/{id}` accepts it.
- **Orchestrator.** A gate step whose resolved policy is `auto` is approved
  by the engine: the run row completes with outcome `approve`, a
  `workflow.gate_auto_approved` event is emitted, and a
  `human_gate_decisions` row is written with `decided_by="policy:<name>"`.
  A gate resolved to `human` pauses exactly as before; `workflow.paused` now
  carries the policy name.
- **Reviewer prompt.** `{previous_output}` (the "Developer Summary") now comes
  from the latest completed *agent* run, not the latest run, because the test
  built-in now sits between develop and review.

## Files changed

- `foreman/workflows.py`, `foreman/settings.py`, `foreman/models.py`,
  `foreman/orchestrator.py`
- `workflows/development.toml`, `workflows/development_secure.toml`,
  `workflows/development_tiered.toml`,
  `workflows/development_with_architect.toml`
- `tests/test_workflow_gates.py` (new, 10 tests), `tests/test_orchestrator.py`,
  `tests/test_cli.py`, `tests/test_workflows.py`,
  `tests/test_runner_lifecycle.py`, `tests/test_output_contract.py`
- `docs/sprints/current.md`, `docs/STATUS.md`, `docs/MANUAL.md`,
  `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `README.md`, `CHANGELOG.md`

## Migrations

- None. Existing tasks paused at a review step resume into the new order at
  their persisted step id; `review`, `code_review`, `security_review`,
  `triage`, `test`, `merge`, and `done` keep their ids.

## Risks

- **Behavior change:** the run sequence for every task now contains a
  `merge_approval` run. Tooling that assumed the old order was updated in
  this branch; external consumers of the events stream will see one more
  step per task.
- **Behavior change:** `merge_approval` defaults to `auto` to preserve
  unattended behavior for existing projects. Production projects that want a
  person to authorize merges must set `merge_approval = human` (or use the
  per-task override). The manual says so.
- **Spec deviation:** `docs/specs/engine-design-v3.md` shows review before
  test. Recorded under "Documented conflicts" in `docs/STATUS.md`.
- A task whose branch fails tests never reaches a reviewer now; reviewers no
  longer act as a substitute for a red test suite.

## Tests

- `./venv/bin/python -m unittest discover -s tests` — 648 passing (was 638;
  +10 in `tests/test_workflow_gates.py`).
- `scripts/validate_repo_memory.py` clean; `git diff --check` clean.

## Acceptance criteria satisfied

- every shipped workflow tests before it reviews and routes test failures
  back to develop,
- every shipped workflow gates the merge behind `merge_approval`,
- an `auto` policy merges with a run row, an event, and a decision record,
- a `human` policy pauses at the gate and `resume_human_gate` continues to
  merge,
- a per-task override forces a human gate on an otherwise automatic project,
- reviewers receive the developer's summary, not the test output.

## Follow-ups

- Sprint 53 slices 5–6.
- Phase 1: extend the policy set (intake triage, notification) and move the
  merge authorization onto the pull request.
