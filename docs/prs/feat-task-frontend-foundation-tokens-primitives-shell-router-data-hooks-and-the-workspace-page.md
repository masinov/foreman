# PR Summary: feat/task-frontend-foundation-tokens-primitives-shell-router-data-hooks-and-the-workspace-page

## Summary

- Sprint 58 slice 1: the structure of the rebuilt frontend (ADR-0020) and its
  first page, the workspace (`docs/design/dashboard-v7/01-workspace.html`),
  at `/dashboard`.
- The pre-v7 application moved, unchanged apart from its base path, to
  `frontend/src/legacy/`, and is served at `/dashboard/legacy` and below.
- No dependency added. No Python change: the server already serves the
  single-page app for every path under `/dashboard`. The only Python file
  touched are tests: the browser e2e fixture now opens the legacy app at its
  new address, and `test_fastapi_dashboard_assets_route_returns_built_bundle`
  follows the entry to the two application chunks (each must be served and
  mount React) instead of expecting React in the entry script.

## Scope

- `app/`: entry that loads the rebuilt or the legacy application by path
  (each its own chunk, so the legacy global stylesheet never reaches rebuilt
  pages); a History API router with real anchors (`Link` leaves new-tab and
  modified clicks and non-app paths to the browser), back and forward, a
  not-found page; the ADR-0020 route table with each route's level, title
  and legacy address; the shell (the word "Foreman", a route-driven
  breadcrumb that names the project, sprint or task from the API, a
  right-hand slot, a 1200px page container, and an empty, closed manager
  slot). Crossing between the two applications with back or forward reloads.
- `api/`: `createApiClient` for `/api/v1`; every failure is an `ApiError`
  whose message is the envelope's sentence (or a sentence saying the server
  could not be reached or did not say why). Resource modules `projects`,
  `sprints`, `gates`, `tasks`, `workspace`. `useResource(key, load)` returns
  `{data, error, loading, reload}`, ignores a response that arrives after a
  newer request, aborts superseded requests, keeps data while reloading.
  `useDelayedFlag` for the 200 ms placeholder rule.
- `ui/`: Button (default, quiet, gold-outline, gold; in-row size), Table
  (header line, faint row lines between rows only, tinted variant, visually
  hidden header option, placeholder rows, own horizontal scroll), Surface,
  StatusDot, Tabs (real links, gold underline, `aria-current`),
  SectionHeading (title, count, note, actions), Mono.
- `styles/`: `tokens.css` with every colour, size, radius and line weight in
  the design README, plus spacing and layout tokens; `base.css`,
  `shell.css`, `ui.css`, `status.css`, `workspace.css`.
- `pages/workspace/`: Needs you across projects (project, kind, task key,
  title linking to its task, what was checked, Approve on human-gate items;
  capped at 5 with "Show all N"; the empty state says nothing needs you) and
  the Projects table (name linking to the project route, repository path and
  default branch, engine state and current task, active sprint linking to
  the sprint route with task counts or "None" with planned count, needs-you
  count, sprint spend). Approve calls `POST /api/v1/tasks/{id}/approve`,
  shows the server's message, and reloads.
- `pages/status/`: the shared "This page is being rebuilt" page with a link
  to the same place in `/dashboard/legacy`, and not-found.

How Needs you is built from today's endpoints (`api/workspace.js`):
`GET /projects`; per project `GET /projects/{id}`, `GET /projects/{id}/sprints`,
`GET /projects/{id}/gates?status=pending`; `GET /sprints/{id}/tasks` only for
sprints whose counts show blocked or triage tasks; `GET /tasks/{id}` only for
tasks at a human gate (for their completion evidence). Items:

- a task with `awaiting_human_gate` → named by its gate step
  ("Merge approval"), what was checked from its completion evidence
  ("tests passed · review approved · b232eb1"), with Approve;
- a task with `blocked_kind == "engine"` → "Unblock", with its blocked reason;
- a task in `triage` → "Accept filed work", with who filed it;
- a pending decision gate → "Sprint order", linking to its project.

## Files changed

- `frontend/src/legacy/*` (moved from `frontend/src/`), `legacy/routing.js`
  (base path), `legacy/mountLegacy.jsx`, `legacy/routing.test.js`
- `frontend/src/app/*`, `frontend/src/api/*`, `frontend/src/ui/*`,
  `frontend/src/pages/**`, `frontend/src/styles/*`, `frontend/src/testing/*`
- `frontend/index.html` (entry path; Inter added to the font request),
  `frontend/vitest.setup.js` (jsdom has no `scrollTo`)
- `foreman/dashboard_frontend_dist/` (rebuilt)
- `tests/test_e2e.py` (opens `/dashboard/legacy`), `tests/test_dashboard.py`
  (built-bundle test follows the entry's chunks)
- `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/TESTING.md`, this file

## Migrations

- none

## Risks

- The workspace makes one request per project for detail, sprints and
  gates, plus task lists and task details where something waits. Fine for a
  handful of projects; the workspace endpoint slice replaces it with one
  request. The page does not change when it does (`api/workspace.js` is the
  seam).
- A dashboard with a token configured: the rebuilt app reads the same stored
  token as the legacy app but has no way to enter one. Without it the page
  shows the API's "Unauthorized" sentence; signing in through
  `/dashboard/legacy` stores the token for both.
- Needs you names a human gate by its step id ("Merge approval",
  "Human approval"), because the API does not expose the gate's policy.
  Approve is offered on any human gate; it is the same endpoint either way.
- No real-browser check is possible on this host (ADR-0020). Checked in
  jsdom and against a live server: `/dashboard`, `/dashboard/legacy/...`,
  `/dashboard/tasks/...` and every built asset answer 200, and the workspace
  loader, Approve and reload, and the error envelope were run against a real
  dashboard on a seeded database. The look needs a person's check against
  `01-workspace.html`.

## Tests

- `npm --prefix frontend test`: 20 files, 134 tests pass (legacy tests
  unchanged and passing).
- `npm --prefix frontend run build`: succeeds; bundle committed.
- `./venv/bin/python -m unittest discover -s tests`: 1128 tests, OK
  (1 skipped: the Playwright e2e module, no browser on this host).
- `ruff check foreman tests scripts`: passes.
- `./venv/bin/python scripts/validate_repo_memory.py`: passes.

## Screenshots or output examples

- Live loader against a seeded server (one project, a task at
  `merge_approval`, one engine-blocked task, one filed task): three Needs
  you items (approval, unblock, accept); Approve answered "Decision
  recorded. No engine is running, so the task waits at `merge` until you
  press Run."; the reload then listed two items. `GET /projects/nope`
  surfaced as "Project not found: nope."

## Acceptance criteria satisfied

- `/dashboard` is the workspace page from live API data; `/dashboard/legacy`
  is the old application, its tests pass.
- `frontend/src/` has `app/`, `api/`, `ui/`, `pages/`, `styles/`; pages do
  not call `fetch`, and no colour, size or line weight is written outside
  `styles/tokens.css` (`styles/rules.test.js` checks both).
- Every ADR-0020 route resolves (`app/routes.test.js`); unbuilt routes render
  the shared being-rebuilt page with a link into `/dashboard/legacy`; an
  unknown path renders not-found; links are anchors; back works
  (`app/App.test.jsx`).
- `useResource` ignores a stale response and surfaces an API error as a
  sentence (`api/useResource.test.jsx`).
- Each primitive has a test; the workspace page has tests for rows from API
  data, the empty Needs you, Approve calling the endpoint and reloading, and
  an API error shown.
- Frontend tests pass, the build succeeds, the rebuilt bundle is committed.

## Follow-ups

Left out because the API has no source for them yet (the workspace API
slice, `task-api-workspace-overview-needs-you-across-projects-project-milestones-and-paged-sprint-lists`):

- **Recent** (milestones) section of the workspace.
- **Last change** column of the Projects table.
- **Backlog** count column of the Projects table (also needs the backlog
  slice).
- Needs you kinds "Approve a plan" and "Approve a merge" as such: the task
  payload should say which policy its human gate is. Until then the kind is
  the step's name.
- Whether pending decision gates (sprint order) belong in Needs you, and as
  which of the four kinds; recorded in `docs/STATUS.md`.
- Sprint and task payloads should carry `project_id` (and the task its
  `sprint_id`), so the breadcrumb can show Workspace / Project / Sprint /
  Task in full and the being-rebuilt page can link a sprint or task to its
  exact place in `/dashboard/legacy` (today it links to the legacy start).

Left out because they belong to other slices:

- **Add project** in the Projects heading (with the project or settings
  slices; adding a project works in `/dashboard/legacy`).
- The person's name in the top bar (identity; until then the design says it
  is the access token's name, which the API does not expose).
- A way to enter the dashboard token in the rebuilt app.
- The mark and its motion (top bar shows the word "Foreman").
- Refreshing hooks from the project or sprint event stream (ADR-0020,
  decision 7); today data reloads on navigation and after an action.
- Field, select, menu, dialog and disclosure primitives, with the pages that
  first need them.
