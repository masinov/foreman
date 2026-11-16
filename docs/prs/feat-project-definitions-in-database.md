# PR Summary: feat/project-definitions-in-database

## Summary

- A project can keep its own roles and workflows. They are TOML text in the
  database, loaded over the shipped definitions (ADR-0024).

## Scope

- Migration 25 and `DefinitionStore`: append-only revisions.
- `foreman/definitions.py`: `project_definitions`, `save_role`,
  `save_workflow`, `remove_definition`; a save is refused unless the whole
  set still loads.
- Role and workflow loaders accept text; tool names and the backend are
  checked for every role, shipped ones included.
- The engine loads a project's definitions when its work starts; the
  dashboard reads, the proposal card, the merge check, gate lookup and the
  CLI read through the same function.
- `foreman role` and `foreman workflow`: `list`, `show`, `set --file`,
  `reset`.
- Not in this branch: the API and the dashboard editor.

## Files changed

- `foreman/definitions.py`, `foreman/store/definitions.py`,
  `foreman/cli/definitions.py` (new)
- `foreman/migrations.py`, `foreman/roles.py`, `foreman/workflows.py`,
  `foreman/_toml.py`, `foreman/orchestrator.py`, `foreman/engine_control.py`,
  `foreman/dashboard_service.py`, `foreman/dashboard_overview.py`,
  `foreman/proposals.py`, `foreman/builtins.py`, `foreman/mutations.py`,
  `foreman/cli/{parser,common,monitor,tasks}.py`, `foreman/store/__init__.py`
- `tests/test_project_definitions.py` (new)
- `docs/adr/ADR-0024-project-definitions-in-the-database.md` (new),
  `docs/STATUS.md`, `docs/ARCHITECTURE.md`, `docs/sprints/current.md`,
  `CHANGELOG.md`

## Migrations

- 25: table `definitions`. Additive.

## Risks

- `resolve_gate_steps` now takes the store and the project; every caller is
  changed.
- The engine changes its role and workflow dictionaries in place at the
  start of a pass. Not seen against a running engine.
- A stored definition that stops loading after an upgrade stops that
  project's engine with the reason.

## Tests

- `tests/test_project_definitions.py`, 22 tests: loading, refusals, removal,
  the engine hook, gate lookup, the CLI.
- Whole suite, ruff, frontend lint, tests and build.

## Screenshots or output examples

```
$ foreman role list foreman
Roles of foreman
code_reviewer | Code Reviewer | changed for this project
developer | Developer | shipped
```

## Acceptance criteria satisfied

- A project runs with its own role or workflow without a change to
  Foreman's files, and a wrong definition is refused with the reason.

## Follow-ups

- Slice 4: the API and the dashboard editor; remove
  `PATCH /api/v1/roles/{id}` and the false sentence on the settings page.
