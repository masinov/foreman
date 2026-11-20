# PR Summary: feat/project-milestones

## Summary

- Slice 3 of "Activity, one stream at three depths" (backlog, owner
  2026-11-21). Milestones (project Activity, workspace Recent) say what a
  lead needs to know: problems, people's decisions, plans confirmed, how
  each merge went, and an engine's time as one row that says how it ended.

## Scope

- `foreman/store/overview.py`: the milestone query gains `plan_confirmed`,
  `task_blocked`, `task_unblocked`, `task_closed`, `task_cancelled`,
  `decision_made`, and `engine_run` / `engine_lost` in place of
  `engine_started` / `engine_stopped`; rows carry `detail`, `ended_at`,
  `how`.
- `foreman/domain/outcome_numbers.py`: `merge_story` (send-backs by cause,
  minutes to merge, cost of one task); `OutcomeStore.outcome_records_for_tasks`;
  the workspace service adds `merge` to each merge milestone.
- Frontend: the kinds and filters (All, Sprints, Merges, Problems, Engine),
  the words for each kind, a detail line under the sentence (two lines at
  most, all of it on hover).

## Files changed

- `foreman/store/overview.py`, `foreman/store/outcomes.py`,
  `foreman/domain/outcome_numbers.py`, `foreman/services/workspace.py`,
  `tests/test_dashboard_workspace_api.py`
- `frontend/src/api/milestones.js`, `pages/shared/milestones.jsx`,
  `pages/shared/Outcomes.jsx`, `styles/lists.css`,
  `pages/project/ProjectPage.test.jsx`
- `docs/ARCHITECTURE.md`, `docs/sprints/backlog.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- The milestone kinds `engine_started` and `engine_stopped` are gone from
  the API; the dashboard was their only reader.
- A decision at a gate is "by a person": the resume does not record who
  (stage 2 identity).

## Tests

- New API tests for every new kind, the merge story and a lost engine
  lease; a page test for every kind's words. Full Python and frontend
  suites, ruff, lint-imports, ESLint, build. Looked at on a copy of the
  database: Foreman's and Assay's Activity and the workspace.

## Acceptance criteria satisfied

- Blocks, decisions, plans, closes and cancels are milestones; a merge says
  its send-backs, time and cost; an engine run is one row and a lost one is
  a problem; the agreed filters.

## Follow-ups

- The owner's review of the three slices.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
