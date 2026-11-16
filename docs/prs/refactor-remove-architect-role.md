# PR Summary: refactor/remove-architect-role

## Summary

- The architect role and `development_with_architect` are no longer shipped
  (ADR-0022, amendment of 2026-11-16). Agreed with the owner.

## Scope

- The two TOML files move to `tests/fixtures/definitions/`. The engine's
  gate tests still need a workflow that starts with a plan and a gate; they
  get it as a project's own definitions (ADR-0024) or beside the shipped set
  in the engine test fixture.
- Migration 26 for a project that was on the removed workflow.
- Docs and a help text that named the architect.

## Files changed

- `foreman/data/roles/architect.toml`,
  `foreman/data/workflows/development_with_architect.toml` (moved to
  `tests/fixtures/definitions/`)
- `foreman/migrations.py`, `foreman/cli/tasks.py`
- `tests/plan_workflow.py` (new), `tests/engine_support.py`,
  `tests/test_{cli,dashboard,dashboard_workspace_api,workflows,workflow_gates,roles,packaging,project_definitions,planning}.py`
- `docs/adr/ADR-0022-...md`, `docs/MANUAL.md`, `docs/STATUS.md`,
  `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- 26: projects on `development_with_architect` without their own copy go to
  `development`; their tasks at `plan` or `human_approval` go back to `todo`.

## Risks

- A project elsewhere that relied on the shipped workflow is moved to the
  standard one and loses its plan step. The pair can be saved back as the
  project's own from the fixture files.

## Tests

- Whole suite; three new tests of migration 26.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- `foreman roles` lists six roles and `foreman workflows` three; no shipped
  file names the architect.

## Follow-ups

- "Approve plans" on a project's settings now means who confirms a planning
  proposal; its wording on the page goes into the audit.
