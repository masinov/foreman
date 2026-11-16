# PR Summary: fix/controls-exercised

## Summary

- Two faults the owner found in the role and workflow editors, and what the
  first pass of clicking every control turned up.

## Scope

- A new role or workflow may start empty (`copy_of: "_blank"`; the payload's
  `blank` holds the two skeletons).
- The role editor's model is a select with "Another model".
- Wording for the merge step's `updated` outcome.
- `scripts/dashboard_shot.mjs`: `--text`, `set:`, `select:`, clicks land in
  the open dialog.

## Files changed

- `foreman/dashboard_definitions.py`
- `frontend/src/pages/settings/{StartFrom,RolesTab,RoleEditor,WorkflowTab,DefinitionDialog}.jsx`,
  `{definitionWords,workflowWords}.js`, `pages/workspaceSettings/WorkflowsList.jsx`
- `scripts/dashboard_shot.mjs`
- tests and fixtures; `CHANGELOG.md`, `docs/STATUS.md`

## Migrations

- none

## Risks

- The list of Claude models offered is a constant in
  `foreman/dashboard_definitions.py`; "Another model" covers the rest.

## Tests

- Both suites; in a real browser on a database copy: an empty role and an
  empty workflow created, a role's model changed from the list.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Neither a role nor a workflow has to start as a copy; the model list opens
  and changes the model.

## Follow-ups

- The rest of the controls (project, backlog, sprint, task).
