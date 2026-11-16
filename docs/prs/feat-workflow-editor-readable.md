# PR Summary: feat/workflow-editor-readable

## Summary

- The workflow editor's step list, redone after the owner could not tell
  from it how a workflow runs.

## Scope

- Label and column heads, step numbers, the start mark, routes that name the
  numbered step, plainer words, fixed columns so every row lines up.
- "Add a step" inserts before the closing step and rewires the sequence.
- No change to what is saved or to the API.

## Files changed

- `frontend/src/pages/settings/WorkflowEditor.jsx`, `definitionWords.js`,
  `workflowWords.js`, `styles/settings.css`, `styles/tokens.css`,
  `Definitions.test.jsx`
- `CHANGELOG.md`

## Migrations

- none

## Risks

- none

## Tests

- Both suites. In a real browser on a database copy: a new workflow from
  empty, one step added and named, saved as develop -> check -> done.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A person can read from the form where a task starts and where it goes
  after each step.

## Follow-ups

- none
