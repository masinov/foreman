# PR Summary: feat/workflow-editor-sequence

## Summary

- The workflow editor shows and edits a workflow as a sequence with its
  exceptions, on top of the soundness rules of ADR-0027.

## Scope

- `WorkflowEditor.jsx` rewritten: the closing step hidden as the end, "on
  to the step below" as a choice that follows the order, defaults for the
  other endings, no carry tick (set by rule on save).
- No change to the API or to what a workflow's text looks like.
- `scripts/dashboard_shot.mjs` finds fields by accessible name.

## Files changed

- `frontend/src/pages/settings/WorkflowEditor.jsx`, `definitionWords.js`,
  `styles/settings.css`, `styles/tokens.css`, `Definitions.test.jsx`
- `scripts/dashboard_shot.mjs`, `CHANGELOG.md`, `docs/STATUS.md`

## Migrations

- none

## Risks

- A workflow with several done steps, or one that is not last, is shown as
  before with that step as a row; the text view covers the rest.

## Tests

- Four step-editor tests rewritten, one added (unchanged save).
- In a real browser on a database copy: each shipped workflow opened and
  saved without a change and compared (identical); a new workflow from
  empty with a Security step added and moved up, saved as develop, test,
  review, security, merge, done.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The order of the list is the order a task goes through; only what departs
  from it is stated.

## Follow-ups

- none
