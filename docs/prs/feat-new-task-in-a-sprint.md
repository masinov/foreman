# feat/new-task-in-a-sprint

## Summary

The owner asked how tasks get into a sprint and noted that a tracker lets a
person add one directly. The dashboard only offered the backlog route.

## Scope

- Sprint page: "New task" opens the task dialog with the sprint as its
  destination and calls the existing `POST /api/v1/sprints/{id}/tasks`. Not
  offered on a finished sprint.
- `NewTaskDialog` takes an optional `sprint`; without it, it files into the
  backlog as before.
- Project sprint list: rows are one line; the goal line is gone from the
  list and stays on the sprint page.
- New sprint dialog: the title hint no longer says "the sprint number"; the
  description says the sprint joins the end of the queue and starts empty.
- Engine row: with the engine running, nothing in hand and an active sprint
  that has no tasks, it says so.

## Files changed

`frontend/src/api/sprints.js`, `frontend/src/pages/project/` (NewTaskDialog,
NewSprintDialog, SprintsTab, EngineRow, ProjectLayout),
`frontend/src/pages/sprint/SprintLayout.jsx`, styles, tests, changelog.

## Migrations

None. No API change.

## Risks

ADR-0021 says work flows filed, accepted, planned. This is a person doing
all three at once, which the CLI (`foreman task add --sprint`) and the API
already allowed; the ADR's rule about agents and other systems is unchanged.

## Tests

`npm --prefix frontend test` (277 pass, 3 new). Frontend only; the Python
suite was not re-run. The sprint page was seen in a screenshot.

## Follow-ups

The dialog does not yet offer complexity or dependencies (sprint 58's
capabilities slice adds them to this dialog).
