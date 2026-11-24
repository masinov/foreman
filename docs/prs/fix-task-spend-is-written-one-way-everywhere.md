# PR Summary: fix/task-spend-is-written-one-way-everywhere

## Summary

- One shared `ui/Spend` (component and `spendWords`) writes every amount of money: mono font, amount before tokens, a zero blank in a table column or list row and "$0.00" in details or headings (owner's rule, 2026-11-24).

## Scope

- Used by the workspace projects table, project sprints and finished sprints, the sprint task list, Details and Activity, and the task's Overview, Steps heading, step Details, run story and Agent side bar.
- Frontend only.

## Files changed

- `frontend/src/ui/Spend.jsx` (+ test); `pages/workspace/ProjectsTable.jsx`, `pages/project/{SprintsTab,FinishedSprints}.jsx`, `pages/sprint/{TaskList,SprintHead,SprintActivity}.jsx`, `pages/shared/ActivityTable.jsx`, `pages/task/{OverviewTab,ActivityTab,AgentPanel,RunStory,runWords,stepFacts}.js(x)`; page tests.
- Docs: design README, `CHANGELOG.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`.

## Migrations

- none

## Risks

- Tables that showed "$0.00" now show blank; intended by the rule.

## Tests

- Frontend lint, vitest (505) and build pass. New: `Spend.test.jsx`, mono-class checks on each page, the run-story order.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- One rule, one shared piece, tests for the piece and each page, docs and PR note updated.

## Follow-ups

- none
