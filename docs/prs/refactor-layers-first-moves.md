# PR Summary: refactor/layers-first-moves

## Summary

- Slice 1 of ADR-0032 (sprint 60, slice 14): the backend becomes a stack of
  layers, and `import-linter` holds it in CI.
- The model and its rules, the repository code, roles and workflows, and the
  engine's root modules move into their layers' packages. No behaviour
  changes.

## Scope

- `.importlinter`: an exhaustive layers contract over `foreman`, with one
  named exception (`mutations` imports the orchestrator; slice 2 removes it).
- `foreman/domain/`: `errors`, `models`, `policy`, `settings`, `outcomes`,
  `guidance`, `leases`, `api_tokens`.
- `foreman/repo/`: `git`, `worktrees`, `context`, `scaffold`.
- `foreman/definitions/`: `roles`, `workflows`, `_toml`, `layers` (was
  `definitions.py`), `gate_steps` (the human-gate step rules and blocked
  kinds, cut out of `engine_control`).
- `foreman/engine/`: `orchestrator`, `builtins`, `judge`, `logs`, `resident`
  (was `serve`), `lock` (was `engine_lock`), `control` (the rest of
  `engine_control`). `task_lease` joined `engine/leasing`.
- `foreman/store/migrations`, `foreman/runner/model_check`.
- Every import in `foreman/`, `tests/` and `scripts/` rewritten by a script
  that resolves each import against the old tree and writes it from the
  module's new place. `mock.patch` targets were rewritten the same way.
  Logger names were left as they were: they are chosen names, not module
  paths.

## Files changed

- 27 modules moved, about 150 files with rewritten imports.
- `.importlinter`, `.github/workflows/ci.yml` (a `lint-imports` step on the
  3.12 job), `pyproject.toml` (`import-linter` in `dev`, Python 3.11+ only).
- `docs/adr/ADR-0032-the-backend-is-built-in-layers.md`, the ADR index,
  `docs/ARCHITECTURE.md` ("Package layers"), `docs/STATUS.md`,
  `docs/TESTING.md`, `docs/sprints/current.md` (slice 14), `CHANGELOG.md`;
  module paths in `docs/MANUAL.md`, `docs/ROADMAP.md` and the sprint files.

## Migrations

- none

## Risks

- Every import path changed. A branch opened before this merge must be
  rebased onto it.
- A running dashboard or resident engine has loaded the old tree. An import
  inside a function of a moved module fails there, so both must be
  restarted after the merge.

## Tests

- full Python suite, ruff, `lint-imports`, repo-memory validation; every
  module and test file imported on its own.

## Acceptance criteria satisfied

- The root of `foreman/` lost 27 modules. What is left there is listed in
  the contract and moves in slices 2 to 5.
- A new module at the root, or an import that goes up a layer, fails CI.

## Follow-ups

- Slices 2 to 5 of ADR-0032.
