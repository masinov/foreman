# PR Summary: feat/outcome-numbers

## Summary

- Outcome numbers per project or sprint, and per agent role and model
  (ADR-0034): passed first time, send-backs by cause, a person's part
  (asked and unasked), cost and tokens per merged task, time to merge.
- `foreman outcomes <project> [--sprint ID] [--json]`;
  `GET /api/v1/projects/{id}/outcomes?sprint=ID`. The manager may run the
  command.

## Scope

- Read-only. Computed from the existing runs and `workflow.*`,
  `engine.merge` and `human.*` events; no new state.

## Files changed

- `foreman/domain/outcome_numbers.py` (new): the pure computation.
- `foreman/store/outcomes.py` (new): `OutcomeStore.outcome_records`.
- `foreman/services/outcomes.py` (new), `foreman/services/__init__.py`.
- `foreman/cli/outcomes.py` (new), `foreman/cli/parser.py`.
- `foreman/api/routers/projects.py`, `foreman/manager/agent.py`.
- `tests/test_outcome_numbers.py` (new).
- ADR-0034, MANUAL, ARCHITECTURE, README, CHANGELOG, sprint file.

## Migrations

- none

## Risks

- A task's entry step is read from its first `step_started` event; a task
  whose events were pruned is counted with what is left.

## Tests

- `tests/test_outcome_numbers.py`: the computation (send-back causes,
  first-time passes, a person asked or unasked, crediting by model, failed
  runs) and the store, service, CLI and API.
- Full suite, ruff, `lint-imports`, repository validator.

## Screenshots or output examples

On the live database, `foreman outcomes assay`: 9 of 9 merged first time,
11 decisions asked of a person with a median wait of 72 s, $0.47 per merged
task. `foreman outcomes foreman`: 21 of 35 merged first time, 28 leaving
merge conflicts aside; 15 of 22 send-backs were merge conflicts.

## Acceptance criteria satisfied

- The numbers the roadmap judges later stages by exist, from the CLI and
  the API, for a project and for a sprint.

## Follow-ups

- Where they show on the dashboard (the owner to agree).
