# PR Summary: fix/dashboard-engine-waiting

## Summary

The owner's report (2026-11-25): the project page said "Engine · Running ·
Nothing to work on: no sprint is active. Activate one under Sprints." with
Pause and Stop enabled. "Running gives the impression that the engine is
actually working … It is confusing, and tbh i do not understand what it
means."

- An engine that is up with no task in hand now reads **Waiting**, with the
  idle tone, so its dot does not breathe. "Running" is kept for an engine
  that works on a task.
- **Pause and Stop are disabled while there is nothing to work on**: no
  active sprint, or an active sprint with no tasks. When the active sprint
  has tasks that are only waiting (blocked, at a gate), both stay offered,
  since Pause still holds back the next task.
- The project page's sentence says what the engine is: "It works through
  the active sprint's tasks, one at a time. No sprint is active: activate
  one under Sprints and it starts."
- The same rule holds in the three places that show the engine: the
  project page's engine row, the top bar's engine menu, and the workspace's
  projects table.
- The design README records the rule, since the design owns the wording
  (ADR-0020) and drew only the "Not running" case.

## Scope

Frontend words and control rules; the design README; the changelog.

## Files changed

- `frontend/src/pages/shared/words.js`: `engineWords(engine)`, the
  `waiting` word, `engineHasWork`, `activeSprintIsEmpty` (moved here from
  `ProjectLayout.jsx`)
- `frontend/src/pages/shared/engineControl.js`:
  `applicableCommands(state, { hasWork })`
- `frontend/src/pages/project/EngineRow.jsx`, `ProjectLayout.jsx`
- `frontend/src/pages/shared/EngineMenu.jsx`
- `frontend/src/pages/workspace/ProjectsTable.jsx`
- `frontend/src/pages/project/ProjectPage.test.jsx`,
  `frontend/src/pages/sprint/SprintPage.test.jsx`
- `docs/design/dashboard-v7/README.md`, `CHANGELOG.md`, this note.

## Migrations

None.

## Risks

- The engine payload gives no "has work" fact of its own, so the page
  derives it from the active sprint's task counts. An active sprint whose
  every task is done also counts as having work, since the sprint still
  waits to be finished; Pause and Stop stay offered there.

## Tests

- `npx vitest run` (whole frontend suite), `npm run build`.
- Screenshots at 1440 and 390 px of the workspace, the project page and a
  sprint page, served from this branch against a copy of the live
  database, where Foreman's engine is up with no active sprint: all read
  "Waiting", with a still dot and the three buttons disabled.

## Acceptance criteria satisfied

- An engine with nothing in hand does not read "Running".
- Pause and Stop are not offered when there is nothing to pause or stop.

## Follow-ups

None.
