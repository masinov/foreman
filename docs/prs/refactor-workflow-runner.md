# refactor/workflow-runner

## Summary

Sprint 57 slice 2c. The workflow step loop is its own class.

## Scope

- `foreman/engine/workflow_runner.py`: `WorkflowRunner` with
  `run_from_step`, the step phases, `pause_for_quota`,
  `write_runtime_context`, the built-in event helpers and the gate policy
  helpers, moved text-exact from `ForemanOrchestrator`.
- `ForemanOrchestrator` builds one as `self.runner` and keeps
  `run_workflow_from_step` as a public method that delegates.
- The sprint doc records the reviewer trial with planted defects.

## Files changed

`foreman/orchestrator.py`, `foreman/engine/workflow_runner.py` (new), one
test call path, changelog, sprint.

## Migrations

None.

## Risks

Behaviour-preserving by construction; 1128 tests pass.

## Tests

Full Python suite and `ruff check`.

## Acceptance criteria satisfied

Slice 2c as written in `docs/sprints/current.md`.

## Follow-ups

`resume_human_gate`, `_run_leased_task`, and one function for an agent
attempt so the corrective retry stops repeating it.
