# PR Summary: feat/workflow-graph

## Summary

- The workflow editor as a graph with one step edited at a time, after the
  owner found the list of dropdowns hard to read and asked for something
  like git's branch drawing.

## Scope

- `WorkflowGraph.jsx`: an SVG of the rail, the lines that leave it (one per
  step they lead into, per direction, laid out in lanes) and each step's
  exceptions in words.
- `WorkflowEditor.jsx`: the graph and, beside it, the chosen step's fields.
  The state, the defaults and what is saved are those of the sequence editor.
- `scripts/dashboard_shot.mjs` clicks `role=button` elements.

## Files changed

- `frontend/src/pages/settings/{WorkflowGraph,WorkflowEditor,DefinitionDialog}.jsx`,
  `definitionWords.js`, `styles/{settings,ui,tokens}.css`, `Definitions.test.jsx`
- `scripts/dashboard_shot.mjs`, `CHANGELOG.md`

## Migrations

- none

## Risks

- A step's name longer than the drawing's text column runs past it.

## Tests

- The step-editor tests, rewritten for the graph. Both suites.
- In a real browser on a database copy: each shipped workflow saved
  unchanged and compared; a new workflow with a Security step added and
  moved up saved as develop, test, review, security, merge, done.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The shape of a workflow, its loops and its skips, can be seen without
  reading a row per ending.

## Follow-ups

- none
