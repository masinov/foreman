# PR Summary: feat/task-project-page-engine-needs-you-the-sprint-queue-with-finished-sprints-and-the-activity-tab

## Summary

- Sprint 58 slice 4. The project page is rebuilt to
  `docs/design/dashboard-v7/` 02, 09 and 11: `/dashboard/projects/{id}`
  (Sprints) and `/dashboard/projects/{id}/activity` (Activity) share one head,
  `ProjectLayout`: title row, engine row, the project's Needs you, and the tabs.
- The workspace page now reads `GET /api/v1/workspace`, `GET /needs-you` and
  `GET /milestones`, and shows each project's backlog count and last change
  and a Recent milestones list.
- The breadcrumb's project is a switcher: a menu of every project with what
  waits in each.
- New primitives: `Menu`, `Dialog`, `Field`, `Disclosure`. New data hook:
  `usePagedList` (server paging).
- Two API additions the page needed and did not have:
  `GET /projects/{id}/sprints?order=recent` (finished sprints newest first;
  the list was queue order only) and `POST /projects/{id}/engine/commands`
  (`pause`, `resume`, `shutdown` for a running engine; Stop had no route).

## Scope

- Engine row: state (Running, Paused, Not running) and a sentence on what it
  means now. Start calls `agent/start` (it spawns an engine when none runs),
  Pause calls `agent/stop`, Resume calls `agent/start` (a `resume`), Stop
  posts `shutdown` to `engine/commands`. A control that does not apply is
  disabled (not running: only Start; running: Pause and Stop; paused: Resume
  and Stop). A refused command shows the API's sentence; an accepted one says
  it was requested and that the state changes when the engine acts on it.
  The head reloads after each command.
- Needs you (shared by both pages): the first five from the server, "Show all
  n" loads the rest; an approve-merge row has the outlined Approve (calls
  `POST /tasks/{id}/approve`, then reloads the list and the head); other
  kinds link to the task.
- Sprints tab: active then planned in run order with goal, task counts
  ("n need you · n done"), dates and spend; planned capped at five; the empty
  planned state; "New sprint" opens a dialog that creates a sprint. Below, a
  closed "Finished sprints n, latest: Sprint 55, 10 Nov" line that opens in
  place: the ten most recent, a filter box (server `q`), "Show 10 more"
  (server paging).
- Activity tab: milestones newest first, 25 at a time with "Earlier", filters
  All, Sprints, Merges, Engine (server `kind`).
- Workspace: projects table gains Backlog and Last change; the Recent list.
- Out of scope: the Backlog tab (next slice; the tab links to the "being
  rebuilt" page), the manager side bar, live updates from the event streams.

## Files changed

- `foreman/store/overview.py`, `foreman/dashboard_service.py`,
  `foreman/dashboard/routers/sprints.py`, `foreman/dashboard/routers/engine.py`,
  `foreman/dashboard/schemas.py`: `order=recent`; the engine command route.
- `tests/test_dashboard_workspace_api.py` (recent order, bad order),
  `tests/test_dashboard_engine_commands_api.py` (new).
- `frontend/src/api/`: `client.js` (`queryString`), `engine.js`,
  `needsYou.js`, `milestones.js` (new); `sprints.js` (paged list, create),
  `workspace.js` (now `GET /workspace`); `usePagedList.js` (new); `gates.js`
  and the old composed `loadWorkspace` removed; tests `resources.test.js`,
  `usePagedList.test.jsx`.
- `frontend/src/ui/`: `Menu`, `Dialog`, `Field`, `Disclosure` with tests;
  `format.js` (`formatDay`, `splitTitle`).
- `frontend/src/app/`: `Breadcrumb.jsx` (switcher), `router.jsx` (`Link`
  forwards its ref), `pages.js`, `App.test.jsx`.
- `frontend/src/pages/project/` (new): `ProjectLayout`, `EngineRow`,
  `SprintsTab`, `FinishedSprints`, `NewSprintDialog`, `ActivityTab`,
  `ProjectPages`, `ProjectPage.test.jsx`.
- `frontend/src/pages/shared/` (new): `NeedsYou`, `milestones`, `words`.
- `frontend/src/pages/workspace/`: `WorkspacePage`, `ProjectsTable`, tests;
  `NeedsYou.jsx` moved to `shared/`.
- `frontend/src/styles/`: `tokens.css` (menu, dialog, field tokens and the
  backdrop colour), `ui.css`, `shell.css`, `workspace.css`, `lists.css` and
  `project.css` (new).
- `frontend/src/testing/`: `workspaceFixture.js` (new payloads),
  `projectFixture.js` (new).
- `foreman/dashboard_frontend_dist/`: rebuilt.
- `docs/ARCHITECTURE.md`, `docs/STATUS.md`, this file.

## Migrations

- none

## Risks

- Needs you no longer lists pending decision gates (a proposed sprint
  order). The needs-you endpoint carries the design's four kinds only; those
  gates are settled from `/dashboard/legacy` until a slice gives them a place
  (recorded in `docs/STATUS.md`).
- Only approve-merge rows have Approve, per the task. An approve-plan item
  links to its task, whose page is still "being rebuilt"; the plan is
  approved from `/dashboard/legacy` until the task page lands.
- A project page reads `GET /workspace` twice (the breadcrumb switcher and
  the head each hold a `useResource`). Correct, and cheap (its query count
  depends on projects only), but a shared cache would halve it.
- The engine row shows the engine's state as last read. After a command it
  reloads once; it does not follow the engine until the live-updates slice.
- A planned "Intake queue" sprint shows in the queue. That is true today
  (Start can activate it); the backlog slice changes what it is.
- No new dependency.

## Tests

- `npm --prefix frontend test`: 26 files, 174 tests pass (Menu, Dialog,
  Field and Disclosure keyboard behaviour; usePagedList paging and stale
  pages; the project page head on both tabs, engine controls and refusals,
  Needs you cap and approve, queue and empty planned state, finished sprints
  paging and filter, the New sprint dialog by keyboard, Activity paging and
  filter; the workspace on the new endpoints; the breadcrumb switcher).
- `npm --prefix frontend run build`: bundle rebuilt and committed; a rebuild
  leaves the tree clean.
- `./venv/bin/python -m unittest discover -s tests`: 1159 tests, OK
  (1 skipped).
- `./venv/bin/python scripts/validate_repo_memory.py`.
- Every URL the pages request was replayed against a copy of the project's
  own database through the ASGI app: all 200, with real sprints, needs-you
  items and milestones (`order=recent` put Sprint 56 first; `q=55` found
  Sprint 55; the `kind` filter returned only sprint milestones).

## Screenshots or output examples

- No browser on the development host (ADR-0020); the look is to be checked
  by a person against 02, 09 and 11.

## Acceptance criteria satisfied

- `/dashboard/projects/{id}` and `/activity` render from live data with one
  head component (`ProjectLayout`) above the tabs.
- Engine controls call the engine endpoints, disable what does not apply and
  show a refused command's sentence. Tested.
- Needs you caps at five with "Show all"; Approve calls the endpoint and
  reloads. Tested.
- The Sprints tab shows only active and planned sprints; finished sprints are
  behind a disclosure that pages and filters on the server. Tested, with the
  empty planned state.
- New sprint works through a keyboard-operable dialog (focus trap, Escape).
  Menu, Dialog and Field each have tests including keyboard behaviour.
- The Activity tab pages and filters milestones. Tested.
- The workspace page uses `GET /api/v1/workspace` and shows backlog count,
  last change and Recent milestones.
- No colours or sizes outside `styles/tokens.css` and no `fetch` outside
  `api/` (`styles/rules.test.js`); frontend tests pass; the bundle is rebuilt
  and committed; the Python suite passes; this file exists.

## Follow-ups

- The design's "Add project" on the workspace is not built (no slice owns it
  yet); projects are added from the legacy dashboard or the CLI.
- Merge milestones in the design name the commit; the milestone payload
  carries no sha, so the Activity tab shows the task key and title only.
- "Sprint 55 finished, 1 task merged" in the drawings: the milestone payload
  has no merged count, so it is left out.
- Pending decision gates have no place in the rebuilt pages (see Risks).
- One shared workspace read for the breadcrumb and the project head.
