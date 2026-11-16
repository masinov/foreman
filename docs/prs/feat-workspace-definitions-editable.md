# PR Summary: feat/workspace-definitions-editable

## Summary

- The workspace's roles and workflows ("Defaults for projects") are edited
  in Workspace settings instead of being a read-only list (ADR-0024,
  amendment of 2026-11-16). Asked for by the owner.

## Scope

- A workspace layer between the shipped files and a project's own
  definitions; checks against every project on a change.
- API routes for the workspace's definitions; the plain role and workflow
  lists read that layer.
- Workspace settings: Workflows and Roles tables with the project's editors.
- Not here: the terminal commands for the workspace layer.

## Files changed

- `foreman/migrations.py` (27), `foreman/store/definitions.py`,
  `foreman/definitions.py`, `foreman/dashboard_definitions.py`,
  `foreman/dashboard_service.py`, `foreman/dashboard/routers/roles.py`
- `frontend/src/api/definitions.js`,
  `pages/workspaceSettings/{DefinitionsSection,WorkflowsList}.jsx`,
  `pages/settings/{RolesTab,RoleEditor,DefinitionDialog}.jsx`,
  `definitionWords.js`, `styles/workspaceSettings.css`
- `tests/test_project_definitions.py`, `tests/test_planning.py`,
  `WorkspaceSettings.test.jsx`, `Definitions.test.jsx`, fixtures
- `docs/adr/ADR-0024-...md`, `docs/STATUS.md`, `docs/sprints/*.md`,
  `CHANGELOG.md`

## Migrations

- 27: table `workspace_definitions`.

## Risks

- A default now changes several projects at once. The save is checked
  against each and every revision is kept.

## Tests

- `WorkspaceDefaultTests`, 7; four frontend tests of the section.
- Against the real API on a copy of the database: a save (the project saw
  it), a refusal with its reason, and a reset.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Everything listed under "Defaults for projects" can be changed where it
  is listed.

## Follow-ups

- `foreman role|workflow set` for the workspace; `foreman init` and Runners
  reading the workspace layer.
