# PR Summary: refactor/long-modules-by-concern

## Summary

- The five longest modules become packages split by concern (ADR-0032).
  Each class is put together from its parts, as `ForemanStore` and
  `Mutations` are, and is imported from where it was. No behaviour changes.

## Scope

- `engine/builtins/`: `base`, `run_tests`, `merge`, `completion`, `done`.
- `engine/orchestrator/`: `base`, `passes`, `tasks`, `gates`.
- `engine/workflow_runner/`: `base`, `checks`, `builtin_steps`,
  `agent_steps`, `transitions`.
- `engine/resident/`: `base`, `commands`, `waiting`, `serve`.
  `terminate_all` is reached through `foreman.runner.process` from both
  parts that stop agents, so tests patch `foreman.runner.process.terminate_all`.
- `cli/tasks/`: `register`, `reads`, `changes`, `lifecycle`.
- Importers that took a name from these modules which they only re-imported
  (`LeaseLostError`, `TaskExecutionError`, `OrchestratorError`,
  `ProjectRunResult`) import it from `engine/errors` or `engine/results`.

## Files changed

- the five packages, their importers, `tests/test_serve.py` (the
  `terminate_all` target), ADR-0032, `docs/ARCHITECTURE.md`,
  `docs/STATUS.md`, `docs/sprints/current.md`, `CHANGELOG.md`.

## Migrations

- none

## Risks

- Seven functions are still over 200 lines (ADR-0032 names them).

## Tests

- full Python suite, ruff, `lint-imports`, `tests/test_layers.py`.

## Follow-ups

- The long functions, each with tests aimed at its branches.
