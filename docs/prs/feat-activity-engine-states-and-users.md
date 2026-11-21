# PR Summary: feat/activity-engine-states-and-users

## Summary

- The owner's second look at the activity views (2026-11-21):
  - "Stopped" followed "Stopped" because the redesign left engine starts out.
    Now every change of the engine's state is listed, starts included, by
    one rule with no exceptions.
  - The sprint's Activity wrote the key with the title, while its task list
    has a Key column. Activity now has a Key column too.
  - "User", not "person", wherever Foreman names someone.
- Also: headings that repeated the tab, a channel name shown as who did
  something, and the "Finish sprints" hint made untrue by
  `fix/engine-waits-for-sprint-activation`.

## Scope

- `foreman/store/overview.py`: `engine_started` at each lease. A `resume`
  requested before a lease and completed after it is the start's (who
  started the engine), not a resume.
- `ActivityTable`: an optional key column (`keyHeader`). The sprint level
  uses Key and Task, the project level Sprint or engine and Title. A phone
  keeps the key and drops the title.
- Words: `userName` ("a user" for a channel), and "user" in the dashboard,
  the CLI, API refusals, the gate role's label, the manager's prompts and
  an agent's guidance sections.
- Headings: "Sprints and engine" (project), "Runs" with count and spend
  (task).

## Files changed

- `foreman/store/overview.py`, `foreman/mutations/{backlog,gates}.py`,
  `foreman/cli/{proposals,parser,outcomes,backlog}.py`,
  `foreman/manager/{digest,agent}.py`, `foreman/services/definition_forms.py`,
  `foreman/domain/guidance.py`, `foreman/engine/output_contract.py`.
- Tests: `test_dashboard_workspace_api.py`, plus the wording in
  `test_guidance.py`, `test_mutations.py`, `test_proposals.py`,
  `test_worktrees.py`, `test_serve.py`.
- Frontend: `ActivityTable.jsx`, `milestones.jsx`, `activityWords.js`,
  `api/milestones.js`, `SprintActivity.jsx`, `project/ActivityTab.jsx`,
  `task/ActivityTab.jsx`, `GeneralTab.jsx`, settings and task words, the
  styles, tests and fixtures.
- Docs: `docs/design/dashboard-v7/README.md` (Words, Activity),
  `docs/ARCHITECTURE.md`, `docs/MANUAL.md`, `docs/STATUS.md`,
  `docs/sprints/backlog.md`, `CHANGELOG.md`.

## Migrations

- none

## Risks

- Wording only, apart from the engine starts: anything that matched the old
  CLI or API sentences must use the new ones.

## Tests

- Engine starts, and a dashboard start naming who started it. Full Python
  and frontend suites, ruff, lint-imports, ESLint, build. Every view checked
  at 1440 and 390 px on a copy of the database.

## Acceptance criteria satisfied

- No stop without a start before it; the key in its own column on the
  sprint page; no "person" where Foreman names someone.

## Follow-ups

- Names on gate decisions and signal stops come with stage 2 identity.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
