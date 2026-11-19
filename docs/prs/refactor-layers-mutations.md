# PR Summary: refactor/layers-mutations

## Summary

- Slice 2 of ADR-0032. The rules for a person's change are a package with
  one part per area, and they no longer import the engine. The layers
  contract lists no exception.

## Scope

- `foreman/mutations/`: `base` (`MutationBase`, `MutationError`, `slug_id`,
  the audit event, the attention turn, the refusal while an engine runs the
  task, worktree removal), `tasks`, `gates`, `backlog` and `sprints`.
  `Mutations` in `__init__` composes the parts, as `ForemanStore` composes
  the store's. Callers are unchanged: `from ..mutations import Mutations,
  MutationError`.
- `mutations/gates.py`: `find_gate_stop` and `record_gate_decision` write a
  gate decision (its system run, `workflow.transition`, `workflow.resumed`,
  the `human_gate_decisions` row, the task moved on). They were in
  `ForemanOrchestrator.resume_human_gate`, and `Mutations.decide_gate`
  imported the orchestrator to reach them. Now the orchestrator calls them.
  It still decides whether it runs the next step itself, and still raises
  `OrchestratorError` with the same messages.
- `foreman/history/`: `records` (`RunRecords`, from `engine/`) and `logs`
  (from `engine/`), below both the engine and the rules for a person's
  change, because both write through them.
- `engine/selection.py` imports `Mutations` at the top. The in-function
  import was there to get round the cycle.

## Files changed

- `foreman/mutations/*`, `foreman/history/*`, `foreman/engine/orchestrator.py`,
  `foreman/engine/selection.py`, the importers of `records` and `logs`.
- `.importlinter` (the `history` layer, the exception removed),
  ADR-0032 ("Where things went (slice 2)"), `docs/ARCHITECTURE.md`,
  `docs/MANUAL.md`, `docs/sprints/current.md`, `CHANGELOG.md`.

## Migrations

- none

## Risks

- A person's gate decision no longer builds a whole `ForemanOrchestrator`.
  It loads the project's workflow through `project_definitions`, which is
  what the orchestrator's `use_project_definitions` did. It writes the task
  through `update_task_engine_state`, as `TaskWrites.save` did.

## Tests

- full Python suite, ruff, `lint-imports`, repo-memory validation.

## Acceptance criteria satisfied

- `lint-imports` keeps the contract with no ignored import.
- No module of `mutations/` is longer than about 360 lines.

## Follow-ups

- Slices 3 to 5 of ADR-0032.
