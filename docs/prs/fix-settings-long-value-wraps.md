# PR Summary: fix/settings-long-value-wraps

## Summary

- A role's or workflow's File row in workspace settings ran out of the
  dialog when the path was long. Reported by the owner on 2026-11-16.

## Scope

- `.setting-row__value` breaks a value that has no spaces
  (`overflow-wrap: anywhere`), so every settings row is covered, not only
  the File row.

## Files changed

- `frontend/src/styles/settings.css`, `CHANGELOG.md`

## Migrations

- none

## Risks

- None known. Values with spaces wrap as before.

## Tests

- Frontend lint, tests and build; the Python suite; the role and workflow
  dialogs looked at with `scripts/dashboard_shot.mjs` at 1280 wide with a
  130-character path.

## Screenshots or output examples

- The path wraps onto three lines inside the dialog.

## Acceptance criteria satisfied

- No settings row's value is wider than its row.

## Follow-ups

- none
