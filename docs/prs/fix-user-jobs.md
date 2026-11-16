# PR Summary: fix/user-jobs

## Summary

- Workspace settings read with the owner, item by item: the group heading
  "Defaults for projects" is removed.

## Scope

- `DefinitionsSection` renders Workflows and Roles as sections of the page.
- `scripts/dashboard_shot.mjs`: `--eval=` for measuring positions.

## Files changed

- `frontend/src/pages/workspaceSettings/{DefinitionsSection,WorkflowsList}.jsx`,
  `pages/settings/RolesTab.jsx`, `styles/workspaceSettings.css`, its test
- `scripts/dashboard_shot.mjs`, `CHANGELOG.md`

## Migrations

- none

## Risks

- none

## Tests

- Both suites; looked at on a copy of the database.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Every heading on the page that looks the same is at the same level.

## Follow-ups

- The rest of the page, with the owner.
