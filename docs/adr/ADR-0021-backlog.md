# ADR-0021: The Backlog Is A Place, Not A Sprint

- Status: accepted
- Date: 2026-11-12
- Deciders: engine team
- Amends: ADR-0013 §4 (the intake queue)

## Context

The design (`docs/design/dashboard-v7/README.md`, `03-project-backlog.html`)
says work flows one way: **filed, accepted, planned into a sprint**. The
engine runs only the active sprint, and a task an agent creates goes to the
backlog, not into the sprint that is running.

The engine had no such place. ADR-0013 §4 put work filed by other systems in
a standing sprint, `<project>-intake`, titled "Intake queue". That sprint was
made `active` whenever no other sprint was, so the engine ran whatever had
been accepted into it. Filed work and planned work were the same thing. The
intake queue was listed among the project's sprints and counted as a
planned one. A task an agent filed with the `task_created` signal went
straight into the active sprint, so agents could grow the sprint they were
working in. Nothing could decline filed work or plan it into a sprint.

ADR-0013 rejected a nullable `tasks.sprint_id` because every reader of
tasks (the engine's selection, the board, sprint views, the digest, the
context projection) would need a second code path for tasks with no sprint.
That reason still holds.

## Decision

### 1. The backlog is a row in `sprints` with `kind = 'backlog'`

`sprints` gains a column `kind`, either `sprint` (every existing row) or
`backlog`. Each project has at most one backlog row (a unique partial
index). The row is created the first time something is filed, with id
`<project>-backlog` and title "Backlog". `tasks.sprint_id` stays `NOT NULL`
and a backlog task points at it. The backlog is found by its kind, never by
its id.

This keeps ADR-0013's reason for avoiding orphan tasks. The cost moves to
the readers of *sprints*: every query that lists, counts, activates or
advances sprints filters `kind = 'sprint'`. There are only a few of these
(`SprintStore`, `OverviewStore`), and they are the queries the engine and
the sprint endpoints already go through.

The database enforces the part that matters: a trigger refuses any backlog
row whose status is not `planned`, so the backlog can never become active
and the engine can never run it, whoever writes. Its stored status is
`planned` only to satisfy the existing status vocabulary. Nothing treats it
as a planned sprint, because every sprint read filters on kind.

### 2. What a backlog task is

| State | `tasks.status` | Meaning |
|---|---|---|
| filed | `triage` | Not accepted yet. Cannot be planned. |
| accepted | `todo` | Accepted, not planned into a sprint. |
| declined | `declined` (new) | A person declined it. Kept, not listed by default. |

`declined` is a new task status. It is not `cancelled`: cancelling stops
work that was going to happen, and declining is a decision about work that
was only proposed. A declined task always lives in the backlog. The engine
never selects anything outside the active sprint, so it never sees one.

The existing `triage` status keeps its name and meaning. It was already
"filed, not accepted", so `foreman task accept` and `POST /tasks/{id}/accept`
work unchanged.

### 3. Operations, all in `foreman/mutations.py`

Each one checks the change is allowed, writes it, and records an audit
event naming who did it and through which surface (`via`, `by`):

- **file** (`backlog.task_filed`). Creates a task in the backlog. The
  project's triage policy (ADR-0014) decides its state: `human` leaves it
  filed and raises one `triage` attention turn, `auto` accepts it at once.
  It is never planned. A person may file work already accepted
  (`accept=True`), because filing it is the person's decision. The CLI,
  the API, intake and agents all file through this one path.
- **accept** (`human.task_accepted`, unchanged). `triage` becomes `todo`.
  A backlog task stays in the backlog.
- **decline** (`human.task_declined`). A filed task, or an accepted one
  still in the backlog, becomes `declined` and moves to the backlog if it
  was not there. A task already planned into a sprint is refused: move it
  back first, or cancel it.
- **plan** (`human.task_planned`). One or more accepted backlog tasks move,
  in one transaction, into a named sprint that is `planned` or `active`, or
  into a new `planned` sprint created by the same operation. Filed or
  declined tasks are refused, and so are completed or cancelled sprints.
  If any task cannot be planned, none are.
- **unplan** (`human.task_unplanned`). A task in a sprint that has not
  started (`todo` or `triage`, with no agent step running) moves back to
  the backlog and keeps its state.

The backlog row itself cannot be activated, completed, cancelled or
deleted. Tasks cannot be added to it by naming it as a sprint
(`foreman task add --sprint`, `POST /sprints/{id}/tasks`).

### 4. Agent-created tasks are filed

The `task_created` signal files the task into the backlog under the
project's triage policy, through the same `file` operation, and records
the agent's role as the filer. With `triage = auto` the task is accepted
at once but still not planned. The running sprint does not grow on its
own.

### 5. Intake files into the backlog

`POST /projects/{id}/intake` keeps its request, response, status codes,
idempotency and its `intake.task_created` audit event. Without a
`sprint_id` the task is filed into the backlog instead of the intake queue
sprint. With a `sprint_id` it still lands in that sprint, as before.

### 6. Surfaces

API under `/api/v1` (ADR-0019 error shape):

- `GET /projects/{id}/backlog`: `status` (`filed`, `accepted`,
  `declined`; repeatable or comma-separated; default filed and accepted),
  `q`, `limit`, `offset`. Filed first, then accepted, then declined. The
  response carries `total`, per-state `counts`, and the project's `triage`
  decision.
- `POST /projects/{id}/backlog`: file.
- `POST /tasks/{id}/decline`.
- `POST /projects/{id}/backlog/plan`: `task_ids` plus a `sprint_id`, or a
  `new_sprint` with `title` and `goal`.
- `POST /tasks/{id}/unplan`.
- `POST /tasks/{id}/accept`: unchanged.

CLI: `foreman backlog list|add|accept|decline|plan|unplan`. `list` takes
`--json`. `accept` is the same operation as `foreman task accept`.

The sprint endpoints and `foreman sprint list` never list the backlog.
`GET /sprints/{id}` answers 404 for it.

### 7. Migration 21

Following ADR-0005, migration 21:

1. adds `sprints.kind` with its vocabulary trigger, the one-backlog index,
   and the trigger that keeps a backlog `planned`;
2. replaces the `tasks.status` vocabulary triggers so they also allow
   `declined`;
3. turns each intake queue into a backlog. For every project with a
   `<project>-intake` sprint it creates `<project>-backlog` and moves the
   queue's `triage` and `todo` tasks into it. Those tasks are the work that
   was filed and waiting. Tasks the queue already started or finished
   (`in_progress`, `blocked`, `done`, `cancelled`) stay where they are, so
   their history and any work in flight are untouched. A queue left with
   no tasks and no decision gates is deleted. A queue that still holds
   tasks stays as an ordinary sprint. If all of them are resolved and the
   queue is not running, it is marked completed.

Every step is a guarded `INSERT ... WHERE NOT EXISTS`, an `UPDATE` or a
`DELETE` keyed on the intake id, so replaying it changes nothing.

## Consequences

- Accepted intake work no longer runs on its own. It waits in the backlog
  until a person plans it into a sprint. This is the behavior change the
  design asks for, and it is the main effect existing users will see.
- Agents cannot add work to the sprint they are running in. Follow-up work
  they find waits in the backlog for the same decision as any other filed
  work.
- `foreman task list` lists tasks by sprint and no longer shows backlog
  tasks. `foreman backlog list` does.
- `task_counts` payloads gain a `declined` key.
- A frontend that rendered the intake queue as a sprint stops seeing it.
  The rebuilt frontend (ADR-0020) reads `GET /projects/{id}/backlog`.
- Each new place that lists sprints must filter `kind = 'sprint'` or go
  through `SprintStore`. The database stops the backlog from becoming
  active. Nothing stops it from being *shown* as a sprint.

## Alternatives considered

- **Nullable `tasks.sprint_id`.** Rejected for ADR-0013's reason, and
  because SQLite cannot drop `NOT NULL` without rebuilding `tasks`, which
  has triggers and foreign keys depending on it.
- **A separate `backlog_items` table.** Rejected. A task would change
  tables when planned, and its runs, events and key would have to follow
  it.
- **Keep the intake sprint but stop activating it.** Rejected. It would
  still be listed as a planned sprint, the engine would still advance into
  it, and the id-suffix convention used to find it is fragile.
- **Convert the intake sprint in place.** Rejected. A queue that was active
  can hold started and finished work, and in-flight work in a place the
  engine never runs would be stranded.
