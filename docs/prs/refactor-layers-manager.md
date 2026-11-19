# PR Summary: refactor/layers-manager

## Summary

- Slice 3 of ADR-0032: the project manager's modules become one package,
  `foreman/manager/`.

## Scope

- `meta_agent` is `manager/agent`; `proposals`, `planning` and `digest` are
  in `manager/`. The contract's manager layer is the package.
- The manager chat's routes (`dashboard/routers/meta.py`) import the
  manager at the top of the module instead of inside each route. No test
  depended on the late import: they replace `_run_claude`, which the
  routes reach through the module either way.

## Files changed

- `foreman/manager/*`, the importers of the four modules,
  `foreman/dashboard/routers/meta.py`, `.importlinter`, ADR-0032,
  `docs/ARCHITECTURE.md`, `docs/MANUAL.md`, `docs/sprints/current.md`,
  `CHANGELOG.md`.

## Migrations

- none

## Risks

- none beyond the path changes; restart the dashboard after the merge.

## Tests

- full Python suite, ruff, `lint-imports`, repo-memory validation.

## Acceptance criteria satisfied

- The manager is one package and one layer.

## Follow-ups

- Slices 4 and 5 of ADR-0032.
