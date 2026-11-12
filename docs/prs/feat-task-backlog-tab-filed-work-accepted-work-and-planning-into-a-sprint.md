# PR Summary: feat/task-backlog-tab-filed-work-accepted-work-and-planning-into-a-sprint

## Summary

- Builds the Backlog tab of the project page at `/dashboard/projects/{id}/backlog` from `docs/design/dashboard-v7/03-project-backlog.html`, on the backlog API of ADR-0021.
- "Filed, not accepted" lists filed work with who filed it and when, and Decline and Accept. A sentence under the heading says who accepts filed work in this project.
- "Accepted, not planned" is a table with a checkbox per row, a select-all, and "Plan selected into" (a new sprint, or any planned or active sprint) with a Plan button that is disabled with nothing selected. A new sprint asks for its title and goal in the Dialog primitive.
- "New task" files a task into the backlog (title, type, description, acceptance criteria).
- 25 rows with "Show more", and a filter box, both answered by the server.

## Scope

- Frontend only. No API or schema change.
- The tab shares the project page head (title row, engine, Needs you, tabs). After any change the tab calls the layout's `changed()`, which re-reads the workspace (so the Backlog tab count, which is `filed + accepted` from the same API the workspace page's backlog column reads, updates) and reloads the list and the sprint choices.
- `usePagedList` passes a page's `meta` through, so the backlog's `counts` and `triage` ride with the page that carries them.
- The triage sentence reads `triage` from the backlog response. That value is the project's resolved triage policy (`PolicyMatrix.resolve("triage")`), so a second request to the policy endpoint would only repeat it.

## Files changed

- `frontend/src/api/backlog.js` (new): list, file, accept, decline, plan.
- `frontend/src/api/usePagedList.js`: `meta` passthrough.
- `frontend/src/pages/project/BacklogTab.jsx`, `NewTaskDialog.jsx`, `PlanNewSprintDialog.jsx` (new); `ProjectPages.jsx`, `ProjectLayout.jsx` (tab gets `changed`); `frontend/src/app/pages.js` (route built).
- `frontend/src/styles/project.css`: class-based styles from tokens.
- Tests: `BacklogTab.test.jsx` (new), `projectFixture.js`, `App.test.jsx` (the "being rebuilt" test used the backlog route, which is now built; it uses project settings, which is not).
- `foreman/dashboard_frontend_dist/`: rebuilt bundle.

## Migrations

- none

## Risks

- Select-all and Plan act on the rows loaded so far, not on every accepted task in the backlog. With more than 25 accepted tasks, "Show more" first.
- Typing in the filter asks the server on each change, as the finished-sprints filter does; there is no debounce.
- The backlog list is one server-ordered list (filed first, then accepted), so with more than 25 filed tasks the first page holds only filed work.
- No dependency was added.

## Tests

- `npm --prefix frontend test`: 194 passed, including BacklogTab tests for: both groups rendering, empty states, Accept and Decline (endpoint, reload, refusal sentence), plan into an existing sprint (body, rows leave, refusal), plan into a new sprint (dialog, validation, body, refusal), New task (body, auto-accepted wording, refusal), checkbox and select-all with accessible names and Plan disabled, server paging, server filtering.
- `npm --prefix frontend run build`, bundle committed.
- `./venv/bin/python -m unittest discover -s tests`, `./venv/bin/python scripts/validate_repo_memory.py`.

## Screenshots or output examples

- n/a (no browser session in this environment; checked against the drawing's structure and wording).

## Acceptance criteria satisfied

- Both groups render from the backlog endpoint; empty states say nothing is filed and nothing is waiting to be planned.
- Accept, Decline, Plan (existing and new sprint) and New task each call their endpoint, reload and show a refusal as a sentence; each is tested.
- Checkboxes and select-all are native checkboxes with accessible names; Plan is disabled with no selection; tested.
- Paging and filtering are server-side and tested.
- Bundle rebuilt and committed.

## Follow-ups

- Declined work is not shown; the API supports `status=declined`, the design draws no place for it.
- Filing as already accepted (`accept: true`) is not offered; the project's triage policy decides.
