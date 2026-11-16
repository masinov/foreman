# PR Summary: fix/workflow-graph-polish

## Summary

- Three things the owner saw in the workflow graph: dead space beside it, a
  floating "Add a step", no direction on the way down.

## Scope

- `WorkflowGraph.jsx`: text column sized to its longest line; a segment and
  arrow tip from a step to the one below only where an ending leads there.
- `WorkflowEditor.jsx` and styles: "Add a step" beside the label; the step's
  column takes the remaining width; choices sized to their text.

## Files changed

- `frontend/src/pages/settings/{WorkflowGraph,WorkflowEditor}.jsx`,
  `styles/{settings,tokens}.css`, `CHANGELOG.md`

## Migrations

- none

## Risks

- none

## Tests

- Both suites; looked at on a copy of the database (tiered workflow).

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Every line in the graph shows its direction; no unused band in the dialog.

## Follow-ups

- none
