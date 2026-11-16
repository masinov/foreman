# PR Summary: feat/definitions-editor

## Summary

- A project's roles and workflows can be edited from the dashboard
  (ADR-0024 amendment). The owner approved the editor's shape on 2026-11-16.

## Scope

- API: `GET /projects/{id}/definitions`, `PUT` and `DELETE` on
  `/projects/{id}/roles/{role}` and `/projects/{id}/workflows/{workflow}`.
  `PATCH /roles/{id}` is removed with its tests.
- `foreman/dashboard_definitions.py`: a definition as form fields, and the
  fields written back into the text they came from.
- A role's prompt must say how its run ends, checked on save.
- `[agent.tools] none = true`; the triage and frontier reviewers use it.
- Frontend: Roles tab, `RoleEditor`, `WorkflowEditor`, `DefinitionDialog`
  (form or text, save, refusal, back to shipped); "Use another workflow"
  offers the project's own workflows; the false sentence on workspace
  settings is corrected; a run's story says "May use no tool".

## Files changed

- `foreman/dashboard_definitions.py` (new), `foreman/definitions.py`,
  `foreman/dashboard_service.py`, `foreman/dashboard/routers/roles.py`,
  `foreman/roles.py`, `foreman/runner/{base,claude_code,codex}.py`,
  `foreman/engine/{agent_step,workflow_runner}.py`,
  `foreman/data/roles/{triage_reviewer,frontier_reviewer}.toml`
- `frontend/src/api/definitions.js`,
  `frontend/src/pages/settings/{RolesTab,RoleEditor,WorkflowEditor,DefinitionDialog}.jsx`,
  `definitionWords.js`, `Definitions.test.jsx` (new); `WorkflowTab.jsx`,
  `ChangeWorkflowDialog.jsx`, `SettingsPages.jsx`, `app/{paths,routes,pages,manager}.js`,
  `api/client.js`, `styles/{settings,tokens}.css`, `testing/settingsFixture.js`
- `tests/test_project_definitions.py`, `tests/test_agent_sandbox.py`,
  `tests/test_dashboard.py`
- `docs/adr/ADR-0024-...md`, `docs/STATUS.md`, `docs/ARCHITECTURE.md`,
  `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- Anyone who can use the dashboard can change what an agent is told and
  which tools it has, for that project (the owner's decision; ADR-0024).
- The workflow form rewrites the whole text; comments in a workflow's own
  text are lost on a form save (the text view keeps them).
- The two reviewers of the tiered workflow lose tools they should never
  have had. Not seen in an engine run.

## Tests

- `tests/test_project_definitions.py`: 15 more (every shipped role and
  workflow through the form and back, the API, refusals).
- `frontend/src/pages/settings/Definitions.test.jsx`: 16.
- One real save, refusal and reset through the API on a database copy; the
  installed CLI started with `--tools ""` reports no tools.
- Looked at with `scripts/dashboard_shot.mjs` at 1440 and 390 wide.

## Screenshots or output examples

- n/a (reviewed by the owner on the running dashboard)

## Acceptance criteria satisfied

- A role's model, tools, ending, limits and prompt, and a workflow's steps
  and what follows each, can be changed from the dashboard for one project,
  and a wrong change is refused with the reason.

## Follow-ups

- The role dialog on workspace settings (shipped defaults) is still the old
  read-only one; it goes into the audit.
- What the architect role is for (slice 5).
