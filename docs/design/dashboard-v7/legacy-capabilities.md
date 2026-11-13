# What the pre-v7 dashboard could do

The application that lived under `frontend/src/legacy/` (served at
`/dashboard/legacy`) was removed on 2026-11-12 by owner decision (ADR-0020,
decision 11). This file is the record of what it could do and see, written
from its source and the endpoints it called before the files were deleted.
The rebuilt dashboard is measured against it: a slice of sprint 58 is not
finished while a line it owns here still says "planned".

Endpoints are under `/api/v1`. Routes are the ADR-0020 routes. Status is one
of:

- **built**: the rebuilt dashboard does it now;
- **slice N**: planned in sprint 58, slice N of the table in
  `docs/sprints/current.md` (a task filed after that table names its task id);
- **no home yet**: no slice or design screen owns it. Each of these is listed
  again at the end, to be placed or dropped on purpose.

The legacy list is what the code did, not what was good. Where the design
(`docs/design/dashboard-v7/`) replaces a behaviour with another one, the row
says so.

## Access

| Capability | Endpoint | Route | Status |
|---|---|---|---|
| A page that asks for an access token when the API answers 401, keeps it in the browser, and sends it as a bearer header | any (401) | every address (the sign-in page takes the page's place) | built. Any request the server answers with 401 brings up Sign in; the token is tried before it is kept; Sign out in the user menu forgets it |

## Workspace (legacy: the Projects page)

| Capability | Endpoint | Route | Status |
|---|---|---|---|
| See every project with its engine state, active sprint and goal | `GET /projects` | `/dashboard` | built |
| See per project counts of done, in progress, blocked and todo work | `GET /projects` | `/dashboard` | built (as needs-you and backlog counts and the active sprint) |
| See a project's token total (sprint, else all time) | `GET /projects` | `/dashboard` | built as sprint spend in dollars |
| See a project's task selection mode and workflow name on its card | `GET /projects` | project settings | slice 10 |
| Open a project | none | `/dashboard/projects/{id}` | built |
| Register a project: name, repository path, workflow | `POST /projects` | `/dashboard`, Projects ("Add project") | built |
| Switch project from the breadcrumb, each with its engine state | `GET /projects` | breadcrumb | built (switcher with counts of items needing you is in the design; the breadcrumb lists projects) |

## Project (legacy: the sprint queue)

| Capability | Endpoint | Route | Status |
|---|---|---|---|
| See the engine's state: running, paused, not running | `GET /projects/{id}/agent/status` | `/dashboard/projects/{id}` | built |
| Run the engine (start, or resume when paused) | `POST /projects/{id}/agent/start` | project page, Engine | built |
| Pause the engine | `POST /projects/{id}/agent/stop` | project page, Engine | built |
| Stop the engine and release it (not in the legacy buttons; the CLI has it) | `POST /projects/{id}/engine/commands` | project page, Engine | built |
| Run one chosen task next | `POST /projects/{id}/agent/start` with `task_id` | task page, More ("Run next") | built |
| See how many tasks sit at a human gate | `GET /projects` | project page, Needs you | built |
| See the active sprint, its progress and the queue of planned sprints | `GET /projects/{id}/sprints` | `/dashboard/projects/{id}` | built |
| See finished sprints, with task counts and spend, behind a disclosure | `GET /projects/{id}/sprints` | `/dashboard/projects/{id}` | built |
| Create a sprint with a title and goal | `POST /projects/{id}/sprints` | `/dashboard/projects/{id}` | built |
| Create a sprint with its first tasks in one step | `POST /projects/{id}/sprints` (`initial_tasks`) | backlog: plan into a new sprint | built (the design gets there by planning backlog work) |
| Drag planned sprints into run order | `POST /sprints/{id}/move` | project page, queue (Order: earlier, later) | built as two buttons per planned sprint, not dragging; the move is one transaction on the server |
| Expand a planned sprint in place to edit its goal, add tasks and remove tasks | `PATCH /sprints/{id}`, `GET`/`POST /sprints/{id}/tasks`, `DELETE /tasks/{id}` | sprint page | built for edit and adding work from the backlog; removing a task is built on the task page (More: cancel, delete) |
| Activate a planned sprint | `PATCH /sprints/{id}` (`status`) | `/dashboard/sprints/{id}` ("Activate sprint") | built |
| Complete a sprint | `PATCH /sprints/{id}` (`status: completed`) | `/dashboard/sprints/{id}` ("Finish sprint") | built |
| Cancel a sprint | `PATCH /sprints/{id}` (`status: cancelled`) | sprint page, More | built |
| Delete a sprint | `DELETE /sprints/{id}` | sprint page, More | built |
| Resolve a pending decision about sprint order: accept the suggested order, keep the current order, or dismiss, with the conflict and the suggested order shown | `GET /projects/{id}/gates`, `PATCH /gates/{id}` | workspace and project pages, Needs you ("Settle sprint order") | built for accept and reject. Reject keeps the current order, so "keep" and "dismiss" are one action; the API still accepts `dismissed` |
| Read the manager conversation, send a message, clear the session, load older messages | `POST /projects/{id}/meta/message`, `GET /projects/{id}/meta/history`, `DELETE /projects/{id}/meta/session` | manager side bar | built |
| A resizable manager panel, collapsed by default | none | manager side bar | built as the design draws it (toggled from the top bar and remembered); resizing is not in the design, dropped |
| See the project's token total in the top bar | `GET /projects/{id}` | none | **no home yet** (the pages show spend in dollars, not tokens) |

## Sprint

| Capability | Endpoint | Route | Status |
|---|---|---|---|
| See the sprint's title, goal, status and totals (tokens, runs, cost, with a note when cost is unknown) | `GET /sprints/{id}` | `/dashboard/sprints/{id}` | built |
| Edit the sprint's title and goal in place | `PATCH /sprints/{id}` | sprint page | built (a dialog, not in place) |
| See the tasks on a board with columns Triage, Todo, In Progress, Blocked, Done | `GET /sprints/{id}/tasks` | `/dashboard/sprints/{id}/board` | built (columns follow the workflow's steps, Queued first and Done last; Triage is now the backlog) |
| See the tasks as a list | `GET /sprints/{id}/tasks` | `/dashboard/sprints/{id}` | built |
| Add a task to the sprint: title, type, description, acceptance criteria, complexity, dependencies | `POST /sprints/{id}/tasks` | sprint page | built as adding work from the backlog; filing a new task is on the backlog tab (title, description and criteria; type, complexity and dependencies are not in the design) |
| Run, pause and resume the engine from the sprint | `POST /projects/{id}/agent/start`, `/agent/stop` | sprint page, engine menu | built |
| Cancel the sprint, delete it | `PATCH`/`DELETE /sprints/{id}` | sprint page, More | built |
| Approve, deny, stop or accept a task from its card | `POST /tasks/{id}/approve`, `/deny`, `/stop`, `/accept` | task page; Needs you; sprint list and board | approve a merge is built (Needs you, sprint list and board); approve, send back (deny), stop and accept are built on the task page |
| Activity stream for the sprint, newest at the bottom, auto-scroll, load older events | `GET /sprints/{id}/events`, `GET /sprints/{id}/stream` | sprint page, Activity | built for steps and loading earlier; live updates are slice 12 |
| Filter activity: All, Agent, Workflow, Decisions, Human | `GET /sprints/{id}/events` | sprint page, Activity | **no home yet** (the design shows milestones and steps, no filter) |
| Live refresh of tasks and events while the page is open | `GET /sprints/{id}/stream` | all pages | slice 12 |
| A banner naming an attention event (a task parked, evidence failed) with "Ask the manager" | `POST /projects/{id}/meta/supervise` | needs you; manager side bar | slice 9 |
| Write guidance for the selected task, read by its next agent step | `POST /tasks/{id}/messages` | task page, Overview | built |

## Task (legacy: the detail drawer)

| Capability | Endpoint | Route | Status |
|---|---|---|---|
| See title, description, acceptance criteria, key, type | `GET /tasks/{id}` | `/dashboard/tasks/{id}` | built |
| See step, branch, worktree path, role, priority, tokens and split, step visits, complexity, model overrides | `GET /tasks/{id}` | task page, Overview | built for step, branch, spend, runs and model overrides (set and cleared in Overrides for this task); worktree path, priority, token split, step visits and complexity **no home yet** |
| See dependencies as chips with their titles | `GET /tasks/{id}` | task page, Overview | **no home yet** |
| See the blocked reason | `GET /tasks/{id}` | task page, the decision | built |
| See the human gate and approve it | `POST /tasks/{id}/approve` | task page; Needs you | built (Needs you and the task page's decision) |
| Send back with a note (deny) | `POST /tasks/{id}/deny` | task page ("Send back") | built |
| See completion evidence: pass or fail, the commit it is about, per-criterion status | `GET /tasks/{id}` | `/dashboard/tasks/{id}/checks` | built (facts and claims from `GET /tasks/{id}/checks`) |
| See the policy that applies to the task, per decision, and where it came from (project, task type rule, task override) | `GET /tasks/{id}` | task page, Overview (Who decides) | built for the gates the workflow has (plan and merge approval) |
| See where the task came from: system, reference, link, reporter | `GET /tasks/{id}` | task page, Overview ("Filed by") and the decision for filed work | built |
| See guidance already written for the task | `GET /tasks/{id}` | task page, Overview | built (each note says whether the agent has read it) |
| Edit title, description, acceptance criteria | `PATCH /tasks/{id}` | task page, Edit | built (and the type) |
| Stop a running task | `POST /tasks/{id}/stop` | task page, More | built |
| Cancel a task | `POST /tasks/{id}/cancel` | task page, More | built |
| Delete a task | `DELETE /tasks/{id}` | task page, More | built |
| Block a task with a reason, unblock it with optional guidance (not in legacy; the CLI had it) | `POST /tasks/{id}/block`, `/unblock` | task page, More and the decision | built |
| See the run history: role, step, model, duration, outcome, tokens | `GET /tasks/{id}` | `/dashboard/tasks/{id}/activity` | built from `GET /tasks/{id}/runs` (step, by, result, took, spend; tokens are not shown) with each run's output and prompt |
| Accept a task filed by another system (triage to todo) | `POST /tasks/{id}/accept` | project page, Backlog | built |
| Decline filed work (not in legacy; added with the backlog) | `POST /tasks/{id}/decline` | project page, Backlog | built |
| See changed files and the diff (not in legacy) | `GET /tasks/{id}/changes` | `/dashboard/tasks/{id}/changes` | built |

## Project settings (legacy: the settings drawer)

| Capability | Endpoint | Route | Status |
|---|---|---|---|
| Autonomy level (supervision) | `GET`/`PATCH /projects/{id}/settings` | `/dashboard/projects/{id}/settings` | slice 10 (replaced by "Who decides") |
| Policy matrix: who decides triage, plan approval, merge approval, notification; task type rules | `GET`/`PATCH /projects/{id}/settings` | project settings, General | slice 10 |
| Allow autonomous task selection | `GET`/`PATCH /projects/{id}/settings` | project settings, General (Task picking) | slice 10 |
| Completion proof gate on or off | `GET`/`PATCH /projects/{id}/settings` | project settings, Workflow ("What finishing requires") | slice 10 |
| Default model, manager model | `GET`/`PATCH /projects/{id}/settings` | project settings, General (Models) | slice 10 |
| Reviewer diff cap (characters) | `GET`/`PATCH /projects/{id}/settings` | none | **no home yet** |
| Criteria judge: base URL, model, API key variable, diff cap (base URL, key variable and test command are shown with the `foreman config` command to change them, not editable) | `GET`/`PATCH /projects/{id}/settings` | none | **no home yet** |
| Default workflow | `GET`/`PATCH /projects/{id}/settings` | project settings, Workflow | slice 10 |
| Merge target branch, spec file | `GET`/`PATCH /projects/{id}/settings` | none | **no home yet** |
| Limits: step visits, cost per task, cost per sprint, time per task | `GET`/`PATCH /projects/{id}/settings` | project settings, General (Limits) | slice 10 |
| Event retention (days) | `GET`/`PATCH /projects/{id}/settings` | project settings, General (Keep history) | slice 10 |
| Test command (read only, with the terminal command to change it) | `GET /projects/{id}/settings` | project settings, General (Tests) | slice 10 |
| Task working copies: count, storage limit, root folder | `GET /projects/{id}/worktrees` | project settings, General (This machine) | slice 10 (the design shows the root; count and limit are **no home yet**) |
| Remove unused working copies | `POST /projects/{id}/worktrees/prune` | none | **no home yet** |

## Workspace-level dialogs

| Capability | Endpoint | Route | Status |
|---|---|---|---|
| Roles: list roles, set a role's model (backend and permission mode shown read only) | `GET /roles`, `PATCH /roles/{id}` | `/dashboard/settings` | slice 11 |

## Everything with no home yet

These are the capabilities the legacy dashboard had that no slice and no
design screen owns. Each needs a decision: give it a slice, or record that
it is dropped and why. The CLI command, where there is one, is the way to do
it meanwhile (docs/MANUAL.md).

1. Built: the sign-in page on a 401 response.
2. Built: register a project from the dashboard (workspace, "Add project").
3. Built: planned sprints are moved earlier or later from the project's
   queue (`POST /sprints/{id}/move`).
4. Built: cancel and delete a sprint (sprint page, More).
5. A project's token total in the top bar.
6. Filtering the activity stream by kind.
7. Task details beyond the design's Overview: worktree path, priority, token
   split, step visits, complexity, dependency chips.
8. Reviewer diff cap, the criteria judge's settings, merge target branch,
   spec file (`foreman config <project-id> --set key=value`).
9. The working copies count and storage limit, and removing unused working
   copies (`foreman worktree list`, `foreman worktree prune`).
10. Adding a task with type, complexity and dependencies in the same form
    (`foreman task add`, which takes them).
