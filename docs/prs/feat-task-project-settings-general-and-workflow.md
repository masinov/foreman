# feat/task-project-settings-general-and-workflow

## Summary

Sprint 58 slice 10. Project settings is a page of its own at
`/dashboard/projects/{id}/settings` (General) and
`/dashboard/projects/{id}/settings/workflow` (Workflow), built from
`docs/design/dashboard-v7/10-project-settings-general.html` and
`08-project-settings-workflow.html`. The breadcrumb is Workspace / project /
Settings. There is no engine row and no Needs you; the engine and the manager
stay in the top bar.

General reads every value from the API and saves through the existing
settings endpoint with one Save that sends only what changed, and Discard. The
API's refusal is shown beside the field it names. Host-level values are shown
as text with the terminal sentence (ADR-0017), with no control. Workflow is
derived from the definition the API returns.

## Scope

- API: `GET /projects/{id}/workflow` now returns transitions, the roles used,
  `source_path`, and what finishing requires (facts and claims);
  `GET /workflows` lists every workflow the same way;
  `GET /projects/{id}/settings` adds `effective` (defaults filled in).
- API: a settings refusal carries `field`; an unknown `workflow_id` is refused.
- Frontend: `pages/settings/` (layout, General form, exception rules, Workflow
  tab, "Use another workflow" confirmation), `styles/settings.css`, the API
  calls in `api/projects.js`, and `ApiError.field`.
- `App.jsx`: the settings routes show the engine menu next to the manager.

## Files changed

- `foreman/dashboard_workflow_reads.py` (new), `foreman/dashboard_service.py`,
  `foreman/dashboard/app.py`, `foreman/dashboard/routers/projects.py`
- `tests/test_dashboard_workflow_api.py` (new)
- `frontend/src/pages/settings/*` (new), `frontend/src/styles/settings.css`
  (new), `frontend/src/testing/settingsFixture.js` (new),
  `frontend/src/api/{client,projects}.js`, `frontend/src/app/{App,pages}.js*`
  and `App.test.jsx`
- `docs/ARCHITECTURE.md`

## Migrations

- none

## Risks

- The test command is host-level, so the API refuses it from the dashboard
  (ADR-0017). The task text lists it under Tests as a field; it is shown there
  as read-only text, and only its timeout is editable.
- "Time per task" is stored as `time_limit_per_task_ms` and "Give up after" as
  `test_timeout_seconds`; the page shows minutes and converts. A value that is
  not a whole number of those units is rounded when saved.
- "Keep history" is three settings (events, runs, prompts) and the design draws
  one control. The page shows three, because they can differ.
- "Tasks in progress at once" is `max_live_worktrees`; empty saves 0, which the
  engine treats as no cap.
- Changing the workflow does not move tasks already underway. The confirmation
  says a task waiting at a step the new workflow lacks cannot continue.
- No dependency added.

## Tests

- `./venv/bin/python -m unittest discover -s tests`: 1273 + new tests, OK.
- `tests/test_dashboard_workflow_api.py`: steps, transitions, roles and source
  of a project's workflow; a different workflow gives other steps and
  requirements; `GET /workflows`; changing and refusing a workflow; the
  `field` on a refusal; `effective`.
- `npm --prefix frontend test`: 269 pass. `ProjectSettings.test.jsx` covers the
  page frame, real values, read-only host values, only-changed Save, Discard,
  rules, the refusal beside its field, the Workflow tables from two different
  workflows, and the confirmation (opened, cancelled, confirmed, refused).
- `npm --prefix frontend run build`: OK. The bundle
  (`foreman/dashboard_frontend_dist`) is ignored and not committed, as the
  sprint rules say; the acceptance line "bundle committed" is not followed.

## Screenshots or output examples

- Opened both routes in headless Chrome against the real server and a seeded database: General showed the stored values (merge approval a person, sprint limit 12.5, a `docs` rule, the test command as text) and the Workflow tab showed the steps, requirements and roles of `development`.

## Acceptance criteria satisfied

- Both routes render from live data on their own page, breadcrumb and tabs, no
  engine row, no Needs you.
- General fields read real values and save through the API; only changed
  fields are sent; Discard restores; a refusal shows beside its field.
- Host-level values are read-only.
- The Workflow tab is derived from the returned definition; a second workflow
  shows different steps and outcomes. New endpoints have Python tests.
- Changing the workflow asks for confirmation and calls the API.

## Follow-ups

- "Evidence files / Add requirement" and "Override for this project" on the
  Workflow tab are left out: the API has nothing to back them.
- The roles table has no "Open" link: there is no role page yet.
- Model choices are free text; the API has no list of models.
- Which step moves on or goes back is read from the order of the steps (a
  transition to an earlier step is "otherwise"). A workflow that loops
  forward would need an explicit marker in the definition.
