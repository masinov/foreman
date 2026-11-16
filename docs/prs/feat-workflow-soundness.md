# PR Summary: feat/workflow-soundness

## Summary

- Workflows are checked as a whole (ADR-0027); the dashboard's empty
  workflow is replaced by one that can finish a task.

## Scope

- `WorkflowDefinition._soundness_errors` and its messages.
- The empty workflow in `foreman/dashboard_definitions.py`.
- No change to the engine's running of a workflow.

## Files changed

- `foreman/workflows.py`, `foreman/dashboard_definitions.py`
- `tests/test_workflows.py`, `tests/test_project_definitions.py`
- `docs/adr/ADR-0027-...md`, `docs/adr/README.md`, `docs/STATUS.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- A workflow a project saved earlier that breaks a rule stops loading. The
  live database has none.

## Tests

- `SoundnessTests`, 9. Both suites.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The eight malformed workflows of ADR-0027 are refused, each with its
  reason; the three shipped workflows load.

## Follow-ups

- The workflow editor as a sequence with declared exceptions.
