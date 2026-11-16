# PR Summary: fix/model-choice-and-step-sizes

## Summary

- The model list's last choice says what it does; the workflow editor's
  step column has controls of one width.

## Scope

- `RoleEditor.jsx`: the wording of the choice that opens the model id field.
- Styles: the step column a fixed width, its controls filling it, the
  workflow dialog sized to its content.

## Files changed

- `frontend/src/pages/settings/RoleEditor.jsx`,
  `styles/{settings,ui,tokens}.css`, `CHANGELOG.md`

## Migrations

- none

## Risks

- none

## Tests

- Both suites; looked at on a copy of the database.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- No choice in the model list reads as a model that does not exist.

## Follow-ups

- A model id is not checked before a task reaches the role.
