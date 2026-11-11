# refactor/engine-package

## Summary

Sprint 57 slice 1. First cut of `foreman/engine/`: code that already stood on
its own is moved out of `foreman/orchestrator.py`, text-exact.

## Scope

- `engine/errors.py`: `OrchestratorError` and its four subclasses.
- `engine/results.py`: `AgentEventRecord`, `AgentExecutionResult`,
  `ProjectRunResult`, `HumanGateResumeResult`, `AgentExecutor`.
- `engine/limits.py`: `resolve_project_settings`, `run_cost_ceiling`,
  `project_timeout_seconds`, `active_run_recovery_timeout_seconds`.
- `engine/model_selection.py`: `ModelSelection` and the two resolvers.
- `engine/output_contract.py`: decision and marker parsing,
  `extract_completion_output`, `contract_retry_reason`,
  `with_retry_instruction`.
- `engine/evidence.py`: `EvidenceBuilder` (`build`, `branch_head`,
  `is_stale`) and `branch_numstat`, `parse_numstat`,
  `summarize_agent_outputs`, `branch_diff_content`.
- `ForemanOrchestrator.build_completion_evidence` stays as the call path
  (tests patch it); `foreman.orchestrator` still exposes the error and
  result names other modules import from it.

Functions that crossed a module boundary lost their leading underscore.

## Files changed

`foreman/orchestrator.py`, `foreman/engine/*` (new), `foreman/builtins.py`,
five test modules (imports only), changelog, sprint.

## Migrations

None.

## Risks

Behaviour-preserving by construction (moved text, renamed references). The
suite is the check: 1064 tests pass unchanged apart from imports.

## Tests

Full Python suite and `ruff check`.

## Acceptance criteria satisfied

Slice 1 as written in `docs/sprints/current.md`.

## Follow-ups

Slice 2: selection and leasing, recovery, and the 750-line step loop.
