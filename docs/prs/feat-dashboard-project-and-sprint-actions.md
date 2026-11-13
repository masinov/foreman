# feat/dashboard-project-and-sprint-actions

## Summary

Three things the old dashboard could do and the rebuilt one could not
(`docs/design/dashboard-v7/legacy-capabilities.md`, items 2 to 4).

## Scope

- Workspace: "Add project" on the Projects heading opens a dialog (name,
  repository folder, workflow) and goes to the new project.
- Sprint page: a More menu with Cancel sprint (planned or active) and Delete
  sprint, each confirmed in a dialog that says what will happen. After a
  delete the page goes to the project.
- Project page: with two or more planned sprints the queue has an Order
  column, earlier and later per planned sprint.
- API: `POST /sprints/{id}/move` with `{"direction": "up" | "down"}`. The
  mutation renumbers the planned sprints in one transaction and repairs equal
  order numbers. Setting `order_index` with two separate PATCH calls would
  have left a half-applied order between them.

## Files changed

`foreman/mutations.py`, `foreman/dashboard_service.py`,
`foreman/dashboard/schemas.py`, `foreman/dashboard/routers/sprints.py`,
`tests/test_sprint_queue_order.py`; in `frontend/src`: `api/projects.js`,
`api/sprints.js`, `pages/workspace/AddProjectDialog.jsx`,
`pages/workspace/WorkspacePage.jsx`, `pages/sprint/SprintHead.jsx`,
`pages/project/SprintsTab.jsx`, `pages/shared/ReasonDialog.jsx` (moved from
`pages/task/`), `ui/Icon.jsx`, styles, tests.

## Migrations

None.

## Risks

The dialogs and the open menu were not seen in a screenshot (the headless
browser cannot click); they reuse the existing dialog and menu primitives.

## Tests

`npm --prefix frontend test`, `./venv/bin/python -m unittest discover -s
tests`, `npm --prefix frontend run build`.

## Follow-ups

Items 1 and 7 to 10 of the capabilities list.
