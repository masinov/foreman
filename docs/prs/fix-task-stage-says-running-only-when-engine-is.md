# fix/task-stage-says-running-only-when-engine-is

## Summary

The sprint's task list and a task's Details called every task with status
`in_progress` "Running, <step>". The status only means the task is part-way
through its workflow; with the engine stopped the page claimed work that was
not happening (seen on FOR-38 with the engine not running).

## Scope

- `stageOf(task, engine)` takes the project's engine from the workspace.
  "Running, <step>" needs the engine running on that task; "Paused at
  <step>" when it is paused on it; otherwise "Stopped at <step>".
- `pages/shared/useProjectEngine.js` reads the engine from the workspace
  answer the top bar already loads.

## Files changed

`frontend/src/pages/sprint/{taskStage.js,TaskList.jsx,SprintLayout.jsx,SprintPage.test.jsx}`,
`frontend/src/pages/task/OverviewTab.jsx`,
`frontend/src/pages/shared/useProjectEngine.js`, `CHANGELOG.md`.

## Migrations

None.

## Risks

Between two steps a running engine may briefly report no current task; the
task then reads "Stopped at <step>" until the next read.

## Tests

`ruff`, the Python suite, frontend lint, tests and build; a screenshot of
sprint 58 with the engine not running.

## Follow-ups

FOR-38's record is still `in_progress` at merge although its branch is in
`main`; closing it needs the engine or a command that does not exist yet
(`docs/sprints/backlog.md`).
