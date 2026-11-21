# PR Summary: fix/engine-waits-for-sprint-activation

## Summary

- The engine no longer activates the first planned sprint on a pass when
  no sprint is active. Assay's sprint 2 was active, empty, half a second
  after it was created, before its plan was confirmed. Owner, 2026-11-21:
  only an explicit activation, or Foreman finishing the sprint before it,
  starts a sprint.

## Scope

- `foreman/engine/orchestrator/passes.py`: the call removed;
  `foreman/engine/sprints.py`: `activate_first_planned` removed.
- Engine row: "Nothing to work on: no sprint is active. Activate one under
  Sprints."
- Unchanged: Foreman finishing a sprint (`auto`) activates the next; Start
  on the engine row, pressed by a person, activates the first planned
  sprint when none is active.

## Files changed

- `foreman/engine/orchestrator/passes.py`, `foreman/engine/sprints.py`
- `tests/test_engine_sprints.py`, `tests/test_engine_selection.py`,
  `tests/test_cli.py`
- `frontend/src/pages/project/EngineRow.jsx`, `ProjectLayout.jsx`,
  `ProjectPage.test.jsx`
- `docs/adr/ADR-0025-who-finishes-a-sprint.md`, `docs/MANUAL.md`,
  `docs/ARCHITECTURE.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- After a person finishes a sprint, the next waits to be activated; before,
  the engine started it on its next pass.

## Tests

- Rewritten: the engine leaves a planned sprint planned (orchestrator and
  `foreman run`); after a person finishes a sprint the next waits until
  activated, then runs. Full suites, ruff, lint-imports, ESLint, build.

## Acceptance criteria satisfied

- A sprint created while the engine runs is not started by it.

## Follow-ups

- none

🤖 Generated with [Claude Code](https://claude.com/claude-code)
