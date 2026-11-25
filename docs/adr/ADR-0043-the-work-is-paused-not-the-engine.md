# ADR-0043: The Work Is Paused, Not The Engine

- **Status:** proposed (owner, 2026-11-25: "Go with it", on the model below;
  the resume rule was settled in the same message)
- **Date:** 2026-11-25
- **Amends:** ADR-0011 (the command table's vocabulary and "a paused
  engine"), ADR-0039 (a paused task does not hold the queue)

## Context

A user controls the work through an "engine", one per project, with Start,
Pause and Stop, and through a sprint's "Activate". On 2026-11-25 the owner
asked what the engine is from a user's point of view, and what starting or
stopping it changes. The honest answers:

- **Work needs two things switched on.** A sprint must be active and the
  engine must be running. Starting the engine with no active sprint also
  activated the next planned sprint by itself (`services/engine.py`), so
  "Activate" and "Start" each sometimes did the other's job.
- **Pause and Stop do the same to the work.** Both cut the running step at
  once and leave the task to run that step again. They differ only in what
  happens to the program: Stop ends it, and is not remembered
  (`engine_is_paused` reads a shutdown as not paused), so a program
  restarted by anything carries on with the work a user stopped.
- **"Run next" can start a whole project.** On a project whose engine is
  off it starts one.
- **A task a user stopped is listed in Needs you,** because Stop blocks it,
  as if Foreman needed the user.
- **The switch is the wrong thing.** "Is the program alive" and "may the
  work go ahead" are two questions. They were the same while one program on
  one machine did a project's work. With several workers, and the machine
  pool the owner has asked for (backlog, owner direction 2), a per-project
  on/off for "the program" means nothing.

The owner and Claude compared three models as trees of actions and
outcomes: today's, one switch per project, and a pause at the level of the
work. The owner chose the third, and then pointed at its weak spot: a
sprint's Resume that leaves its paused tasks paused does nothing when all
of them are paused. The rules below close that.

## Decision

### 1. A pause is put on the work, at one of three levels

| Level | Where the controls are | What a pause there holds |
|---|---|---|
| Workspace | workspace page header | every task of every project |
| Sprint | sprint page header; the project page header and the top bar show the active sprint's | every task of the sprint |
| Task | task page header | that task |

A project has no pause of its own. It has one active sprint, so a project
pause would be the sprint's under another name. When several sprints of a
project can run at once, the project page shows each one's.

### 2. Two ways to pause, one paused state, one Resume

- **Pause.** A step that is running finishes. Then no new step starts in
  what is paused. Nothing is cut.
- **Stop.** A step that is running is cut now: its agent's process group is
  ended and its run settled as killed, as today. The step runs again from
  its start on Resume. The cut visit is not counted against the step's
  visit limit, as with `steer_task` (ADR-0011, 2026-11-16): a user cut it,
  it did not fail. Stop is a red button and asks for no confirmation,
  because what it cuts is one step and that step runs again.
- **Resume** follows either. Both end in the same state, paused; the status
  line says which way it was paused.

### 3. The rules that make every button do something

1. **A pause passes down, never up.** A paused sprint holds its tasks.
   Pausing every task of a sprint does not pause the sprint: it stays
   started and says "Nothing to run · 3 tasks paused".
2. **Resume releases everything at and below its level.** Resume on a
   sprint lifts the sprint's pause and every pause on its tasks. Resume all
   lifts every pause in the workspace. So Resume is never a button that
   leaves everything as it was.
3. **Resume is offered wherever something at or below is paused;** Pause
   and Stop wherever something at or below can run. A started sprint with
   one task paused shows Pause, Stop and Resume: Pause holds everything in
   it, Resume releases everything in it.
4. **Resume asks no confirmation; its toast says what it released:**
   "Resumed sprint 64, FOR-66 and FOR-67." Resuming is undone by pausing
   again, so a question before it would only be friction (owner,
   2026-11-25).
5. **Nothing is resumed past a pause above it.** A task of a paused sprint
   offers no Resume; in its place the page says "Sprint 64 is paused", with
   a link to it. The same holds for a sprint under a paused workspace.
6. **A pause lasts until someone resumes it.** A restart, a reboot or a
   crashed worker does not lift it. Starting a sprint under a paused
   workspace starts it; its status line says it waits for the workspace.

### 4. What the other actions do

- **Start sprint** replaces "Activate sprint". It is the only way a sprint
  starts. Nothing starts a planned sprint by itself any more.
- **Run next** only changes the order: the task is first in line, and runs
  when nothing above it is paused. While it waits it reads "Runs next", and
  where something above is paused, "Runs next when sprint 64 resumes".
- **Stop on a task leaves it paused, not blocked.** Blocked stays what
  Foreman says when it needs a user (a failure, a loop limit, a branch
  violation). A task a user stopped is not in Needs you.
- **Block leaves the task page's menu.** On a task not yet started, Pause
  does what Block did there, without putting it in Needs you. Foreman's own
  blocks and the manager's proposal to block a task stay.
- **A paused task does not hold the queue** (amends ADR-0039, which lets
  only a task waiting for a decision hold it). The sprint goes on with its
  other tasks, as it does past a blocked one. On Resume the task is first in
  line, and its branch is refreshed from the default branch before its next
  step, as any task's is (ADR-0012).
- **A decision made while paused is recorded and waits.** Approving a merge
  in a paused sprint moves the task to Merge, which runs on Resume: "Approved
  FOR-51. It goes on with Merge when sprint 64 resumes."

### 5. What the page says

One status line per level, the same words wherever it is shown (the
sprint header, the project header, the top bar, a row of the workspace's
projects table):

- "Working on FOR-65 · Develop"
- "Pausing · Develop is finishing" (Stop stays offered, for a step taking
  too long)
- "Paused by you at 14:02"
- "Stopped by you at 14:02 · Develop runs again"
- "Nothing to run · 3 tasks paused"
- "Waiting · no sprint started"
- "Waits for the workspace · paused by you at 14:02"

A task's Status keeps its existing shape: "Paused · Develop", with who
paused it and when on hover. "Stopped · Develop" (no engine) and "Waiting ·
Develop" (the engine is on another task) keep their meanings.

### 6. The engine leaves the page

The Engine row on the project page, the engine menu in the top bar, the
engine's Start, Pause and Stop, and the word "engine" leave the dashboard.
The program that runs the work is called a **worker**.

- **While no worker holds a project,** the project's status line says so,
  in the place of the others: "Not running · no worker for this project",
  with **Start worker**. That is the one worker control on the page. It is
  a fault to fix, not a switch for the work, and the work's pauses are
  untouched by it.
- **A supervisor will keep workers running** (a systemd user unit per
  project, restarting with a growing wait; a separate slice). With it, the
  line above appears only after its restarts have given up, and its button
  reads Restart.
- **A Workers view** in workspace settings (which workers are alive, idle
  or on which task, and their restart) comes with the supervisor or with
  the machine pool, whichever is first.
- **The command line keeps worker control:** `foreman serve` starts one and
  `foreman engine shutdown` ends one. Ending a worker does not pause the
  work: another worker, or the supervisor, carries on with it.

### 7. How it is stored, and how the worker hears it

A pause is state that every page shows, not a message to a program, so it
is a row, not a command.

- **A `pauses` table** (a migration): `id`, `scope` (`workspace`, `sprint`,
  `task`), `scope_id` (null for the workspace), `project_id` (null for the
  workspace), `mode` (`finish_step`, `now`), `requested_by`,
  `requested_at`, `released_by`, `released_at`. A level has at most one
  unreleased pause. Resume releases rows (rule 2) in one transaction.
- **The worker reads it where it reads commands today:** before each step,
  and on every tick of an agent step (ADR-0011's poll sites). Before a step,
  any unreleased pause covering the task parks it: the task stays
  `in_progress` at that step and releases its lease. On a tick, a `now`
  pause covering the running task cuts the step. A `finish_step` pause is
  not acted on until the step ends.
- **Choosing a task skips every task a pause covers.** When every candidate
  is covered, the pass ends with the stop reason `paused`, and a resident
  worker waits on `data_version` as it does now.
- **The command table keeps what is a message to a worker:** `run_task`,
  `steer_task` and `shutdown`. `pause`, `resume` and `stop_task` are
  retired: the API and the CLI write and release pauses instead
  (`foreman pause <project> [--sprint S | --task T] [--now]`,
  `foreman resume …`, with the workspace when neither is given).
- **Existing state is carried over.** A project whose engine stands paused
  when the migration runs gets a pause on its active sprint, mode
  `finish_step`, requested by whoever paused the engine.

## Consequences

- **One way to start work:** start a sprint. One way to hold it: pause, at
  the level you mean. Every Resume releases something.
- **A user's stop is never lost to a restart,** because it is a pause and
  pauses outlive programs. This is why the engine's Stop goes before a
  supervisor comes: today a supervisor would restart a stopped engine and
  carry on with the work.
- **Pause is slower than it was.** It waits for the running step, which may
  take many minutes. The status line says "Pausing" with the step, and Stop
  stays offered meanwhile.
- **A paused task's branch can fall behind** while the sprint goes on. The
  refresh before its next step merges the default branch in; a conflict is
  handled by the workflow as for an unblocked task.
- **Two programs now share pause state through the database only,** which is
  the product's premise (ADR-0011): a dashboard on another host, the CLI,
  the intake API and every worker read the same rows.
- **The design changes** (`docs/design/dashboard-v7/README.md`): the Engine
  bullet becomes the status line and the three levels' controls; "Activate"
  becomes "Start sprint"; the task Status bullet gains who paused; the
  toast for an approval in a paused sprint; "the engine dot" in Mark and
  motion becomes "the status dot while something is working". The drawing
  `02-project-sprints.html` loses its engine row.

## Alternatives considered

- **Keep the engine as the switch.** Rejected for the reasons in Context:
  two switches for one job, a Pause and a Stop that differ only for the
  program, and no meaning once a project has several workers.
- **One switch per project, no sprint or task pause.** Simple, with no
  combinations, but a user cannot hold one task to look at it while the
  others go on, and with parallel workers inspecting one task would halt
  all of them.
- **Resume releases only its own level.** Rejected by the owner: a sprint
  whose tasks are all paused would offer a Resume that does nothing.
- **Pause cuts the step, as today.** Rejected: the common wish is "let it
  finish, then hold", and cutting throws away a step's work. Stop is there
  for the urgent case.
- **A fourth level, the project.** Redundant while a project has one active
  sprint; the project page shows the sprint's controls instead.
- **Keep pause as commands in `engine_commands`.** Rejected: a command is
  addressed to a program and expires with it (ADR-0011 rejects a pending
  `pause` when a new engine starts), while a pause must outlive programs and
  be visible on every page.

## Order of work

1. The `pauses` table, the worker reading it, and the CLI. Retire the
   engine's Stop on the dashboard in the same slice, since a stop must
   become a pause before anything restarts workers.
2. The dashboard: the status line, Pause, Stop and Resume at the three
   levels, Start sprint, Run next as order only, the engine row and menu
   removed, Start worker on the fault line. The design README and drawing
   change with it.
3. Before relying on restarts: a test that a worker killed hard (SIGKILL)
   leaves no agent process running. Then the supervisor, and the Workers
   view.
