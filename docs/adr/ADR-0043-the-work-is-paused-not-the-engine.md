# ADR-0043: The Work Is Paused, Not The Engine

- **Status:** proposed (owner, 2026-11-25: "Go with it", on the model below;
  the resume rule was settled in the same message)
- **Date:** 2026-11-25
- **Amends:** ADR-0011 (the command table's vocabulary and "a paused
  engine"), ADR-0039 (a paused task does not hold the queue; a request to
  run a task does not pass a pause), ADR-0025's amendment on finishing
  sprints (no pause may hold a sprint Foreman finishes or starts)

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
of them are paused. The rules below close that. A second opinion
(Fable 5.2, 2026-11-25) then found that a higher pause erased a user's
deliberate holds, that Stop could claim a step was cut when it was not,
and that a paused sprint still finished and started the next one. The
owner answered the last (2026-11-26): "Pause should pause the task and
everything downstream that depends on it", and Foreman should finish and
start sprints itself "unless they have been deliberately blocked".

## Decision

### 1. A pause is put on the work, at one of three levels

| Level | Where the controls are | What a pause there holds |
|---|---|---|
| Workspace | workspace page header | every sprint and task of every project |
| Sprint | sprint page header; the project page header and the top bar show the active sprint's | the sprint and every task in it |
| Task | task page header | that task |

A project has no pause of its own. It has one active sprint, so a project
pause would be the sprint's under another name. When several sprints of a
project can run at once, the project page shows each one's.

### 2. A pause holds what comes after

A pause holds the thing paused and everything downstream of it: whatever
cannot start until it is done (owner, 2026-11-26). Downstream is the
dependency chain that already exists:

- **a task's next step,** built-in steps included (tests, Merge, Mark
  done), so a paused task never becomes Done;
- **the tasks that wait for it** ("Waits for", set on a task before it
  starts; ADR-0039 and `foreman/engine/selection.py`). They wait until it
  is done, so they wait through its pause;
- **the sprint's finish,** which waits for every task in it;
- **the next sprint's start,** which waits for that finish.

So a paused sprint is neither finished nor followed by the next one. When
its work is all done it reads "Paused · ready to finish"; on Resume it is
finished and the next sprint starts, where the project lets Foreman finish
sprints (`sprint_completion = auto`). Foreman finishes and starts sprints
by itself unless a pause holds them, on the sprint or the workspace.

Tasks of the same sprint that do not wait for a paused task go on: a task
pause pauses only that task and what depends on it.

### 3. Two ways to pause, one paused state, one Resume

- **Pause.** A step that is running finishes. Then nothing downstream
  starts. Nothing is cut. Offered wherever something may run.
- **Stop.** A step that is running is cut now. Offered only while a step is
  running in what it would stop; with nothing running, Pause is all there
  is to do.
  - An agent step's process group is ended and its run settled as killed,
    as today. A test run's process is ended the same way.
  - A merge is never cut: cutting it half way is worse than waiting for it.
    It finishes, then the hold applies.
  - The status line reads "Stopping · Develop" until the run is settled,
    and "Stopped" only after.
  - The step runs again from its start on Resume. The cut visit is not
    counted against the step's visit limit, as with `steer_task` (ADR-0011,
    2026-11-16): a user cut it, it did not fail.
  - Stop is a red button and asks for no confirmation, because what it
    cuts is one step and that step runs again.
- **Resume** follows either. Both end in the same state, paused; the status
  line says which way it was paused.

### 4. The rules that make every button do something

1. **The last action wins, at and below where it is taken.** A Pause or a
   Resume applies to its level and everything below it, and replaces what
   was said there before.
   - Pause on a sprint holds every task in it, including tasks added
     later, and undoes a Resume given to one of them before.
   - Resume on a task in a paused sprint lets that task run. The sprint
     stays paused for the others.
   - Resume on a sprint releases it and every task in it. Resume all
     releases everything in the workspace.
   - The workspace works the same way: after Pause all, resuming one
     sprint or one task lets only that run.
   So every Pause and Resume is on the page where the user is, and does
   what it says there. No control is hidden because of a level above.
2. **A pause is a short hold; Block is the long one.** Any Resume above
   releases a task's pause. A task a user means to park for days is
   blocked, with a reason: it is listed in Needs you, and only Unblock
   lifts it. No Pause or Resume touches a block.
3. **A pause passes down, never up.** Pausing every task of a sprint does
   not pause the sprint: it stays started, and its status line says
   "3 tasks paused".
4. **Resume is offered wherever something is held:** at the level of a
   pause, below it (where it lets one thing run, rule 1), and above it
   (where it releases what is below). A started sprint with one task paused
   shows Pause and Resume: Pause holds everything in it, Resume releases
   everything in it. A sprint already paused shows Resume, and Stop while a
   step of it still runs.
5. **Resume asks no confirmation; its toast says what it released,** by
   key: "Resumed the sprint, FOR-66 and FOR-67." Past three keys it says
   "and 4 more". Resuming is undone by pausing again, so a question before
   it would only be friction (owner, 2026-11-25).
6. **An exception is shown above it.** A paused sprint with one task let
   run says "Paused · except FOR-65", with two "Paused · except 2 tasks".
7. **A pause lasts until someone resumes it.** A restart, a reboot or a
   crashed worker does not lift it. Start sprint is not a Resume: a sprint
   started under a paused workspace waits, and says "Paused · workspace".

### 5. What the other actions do

- **Start sprint** replaces "Activate sprint". It is how a user starts a
  sprint; Foreman starts the next one itself only as §2 says.
- **Run next** puts a task that may run first in line. A held task shows
  Resume instead, never both: one button per intent. A `run_task` request
  for a task that is held when the worker takes it up is rejected, saying
  so; ADR-0039's rule 5, that a request to run a named task passes over a
  task waiting for a decision, does not pass over a pause.
- **Stop on a task leaves it paused, not blocked.** Blocked stays what
  Foreman says when it needs a user (a failure, a loop limit, a branch
  violation) and what a user sets with a reason (rule 4.2). A task a user
  stopped is not in Needs you.
- **A paused task does not hold the queue** (amends ADR-0039, which lets
  only a task waiting for a decision hold it). The sprint goes on with
  the tasks that do not wait for it, as it does past a blocked one; after
  a Stop that is seconds later. On Resume the task is first in line, and
  its branch is refreshed from the default branch before its next step, as
  any task's is (ADR-0012). A task paused at a gate is the same: pausing it
  releases the queue, and the collisions ADR-0039 removed are possible for
  that task, as for a blocked one.
- **A decision made while paused is recorded and waits.** Approving a merge
  in a paused sprint moves the task to Merge, which runs on Resume:
  "Approved FOR-51. It merges on Resume." A task paused while it waits for
  a decision stays in Needs you, and its Status reads "Paused · Approval".

### 6. What the page says

**No name in a status line, a toast or a button.** A sprint's or a
project's title is free text of any length; these places are fixed and
short. They use fixed words, task keys, dates and times. Which sprint, who
acted and the full time are on hover; at phone width a tap on the status
line shows them.

One status line per level, the same words wherever it is shown (the
sprint header, the project header, the top bar, a row of the workspace's
projects table). When more than one is true, the first in this list wins:

- "Stopping · Develop"
- "Pausing · Develop finishing" (Stop stays offered, for a step taking
  too long)
- "Stopped · 14:02" (hover: the step that runs again)
- "Paused · 14:02", "Paused · 24 Nov" after the day it was set
- "Paused · ready to finish"
- "Paused · workspace"
- "Paused · except FOR-65"
- "Working · FOR-65 Develop", with "· 3 tasks paused" after it when some
  are
- "3 tasks paused" (nothing runs, the sprint is not paused)
- "Not started"

**A worker fault stands beside the line, not in its place:** "Paused ·
14:02 · no worker". The user sees both that the work is paused and that
no program could run it.

**A task's Status** keeps its existing shape: "Paused · Develop", with who
paused it, at which level and when on hover. "Waiting · Develop" (another
task is running) keeps its meaning; a task that waits for another reads
"Waiting · FOR-65". "Stopped · Develop" now means a user stopped it.

**A task shows what waits for it:** beside "Depends on", its Overview lists
"Needed by", so a user sees what a Pause on it will hold.

### 7. The engine leaves the page

The Engine row on the project page, the engine menu in the top bar, the
engine's Start, Pause and Stop, and the word "engine" leave the dashboard.
The program that runs the work is called a **worker**.

- **While no worker holds a project,** the status line carries "no
  worker", with **Start worker**. That is the one worker control on the
  page. It is a fault to fix, not a switch for the work, and the work's
  pauses are untouched by it.
- **A supervisor will keep workers running** (a systemd user unit per
  project, restarting with a growing wait; a separate slice). With it,
  "no worker" appears only after its restarts have given up, and the
  button reads Restart.
- **A Workers view** in workspace settings (which workers are alive, idle
  or on which task, and their restart) comes with the supervisor or with
  the machine pool, whichever is first.
- **The command line keeps worker control:** `foreman serve` starts one and
  `foreman engine shutdown` ends one. Ending a worker does not pause the
  work: another worker, or the supervisor, carries on with it.
- **A crashed worker's run is settled by the next worker** (crash recovery,
  as today). Until then a "Pausing" or "Stopping" line stays, with "no
  worker" beside it.

### 8. How it is stored, and how the worker hears it

A pause is state that every page shows, not a message to a program, so it
is a row, not a command.

- **A `work_switches` table** (a migration), at most one row per level:
  `scope` (`workspace`, `sprint`, `task`), `scope_id` (the fixed id
  `workspace` for the workspace, never null, so the unique index on
  `(scope, scope_id)` holds), `project_id` (null for the workspace),
  `state` (`paused`, `running`), `mode` (`finish_step`, `now`; for
  `paused`), `set_by`, `set_at`.
- **An action** replaces its level's row and deletes the rows below it
  (rule 4.1), in one transaction. Each action is also an event, which is
  the history. A `running` row is written only as an exception under a
  pause (a task resumed in a paused sprint); a Resume with nothing paused
  above deletes its level's row instead.
- **The most specific row decides.** A task is held when the row nearest
  to it (its own, else its sprint's, else the workspace's) is `paused`.
  Because every action deletes the rows below it, this gives the
  last-action-wins answer without comparing times written by different
  processes' clocks. One function, `is_held`, answers it for the API, the
  pages and the worker.
- **Rows do not outlive what they describe.** A task's row is deleted when
  it moves to another sprint or the backlog, is closed, or is reopened. A
  sprint's row is deleted when it is finished; reopening a sprint starts
  it unpaused.
- **The worker reads it where it reads commands today:** before each step,
  and on every tick of an agent step (ADR-0011's poll sites), and, for
  Stop, while a test run waits. Before a step, a held task is parked: it
  stays `in_progress` at that step and releases its lease. A hold with mode
  `now` cuts the running agent step or test run; a hold with mode
  `finish_step` is not acted on until the step ends.
- **Choosing a task skips every held task,** and finishing a sprint or
  starting the next checks the sprint's and the workspace's rows first
  (§2). When nothing may run, the pass ends with the stop reason `paused`,
  and a resident worker waits on `data_version` as it does now.
- **The command table keeps what is a message to a worker:** `run_task`,
  `steer_task` and `shutdown`. `pause`, `resume` and `stop_task` are
  retired: the API and the CLI write switches instead
  (`foreman pause <project> --sprint S | --task T [--now]`,
  `foreman pause --all [--now]`, and `foreman resume` with the same
  choices). Run next queues `run_task` in the same transaction that checks
  the task is not held.
- **Existing state is carried over.**
  - A project whose engine stands paused, or was last stopped with the
    engine's Stop (which `engine_is_paused` reads as not paused), gets a
    `paused` row on its active sprint, mode `finish_step`, set by whoever
    did it.
  - A task blocked as "Stopped by …" becomes a paused task: `in_progress`
    at its step, no blocked reason, a `paused` row of its own.

## Consequences

- **One way to start work:** start a sprint; after that Foreman carries on
  from sprint to sprint where the project lets it. One way to hold work:
  pause, at the level you mean, and what depends on it waits too. Every
  Resume releases something.
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
- **Dependencies stay within a sprint.** "Waits for" names tasks of the
  same sprint, and sprints follow each other in queue order. That is all §2
  needs. Dependencies across sprints are recorded in the backlog, for when
  sprints can run side by side.
- **The design changes** (`docs/design/dashboard-v7/README.md`): the Engine
  bullet becomes the status line and the three levels' controls; "Activate"
  becomes "Start sprint"; the task Status bullet gains who paused and
  "Waiting · FOR-65"; the Overview gains "Needed by"; the toast for an
  approval in a paused sprint; "the engine dot" in Mark and motion becomes
  "the status dot while something is working". The drawing
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
- **A pause above hides Resume below.** Rejected by the owner: a user could
  not let one task of a paused sprint run without resuming the sprint and
  pausing every other task, the page would send them elsewhere to act, and
  a task named with Run next would be ignored.
- **Pause replaces Block.** Proposed in the first draft and withdrawn: a
  pause has no reason, is lifted by any Resume above, and is in no list,
  so a task parked for days would be released by a ten-minute pause of its
  sprint and forgotten in between.
- **A paused sprint may finish, and the pause moves to the next.** Rejected
  for the simpler rule of §2: what is paused does not finish.
- **Pause cuts the step, as today.** Rejected: the common wish is "let it
  finish, then hold", and cutting throws away a step's work. Stop is there
  for the urgent case.
- **A fourth level, the project.** Redundant while a project has one active
  sprint; the project page shows the sprint's controls instead.
- **Keep pause as commands in `engine_commands`.** Rejected: a command is
  addressed to a program and expires with it (ADR-0011 rejects a pending
  `pause` when a new engine starts), while a pause must outlive programs and
  be visible on every page.
- **Decide by the newest `set_at`.** Rejected: times are written by
  different processes, and commit order can differ from their clocks; the
  most specific row gives the same answer with no clock.

## Order of work

1. The `work_switches` table, `is_held`, the worker reading it (built-in
   steps and the sprint's finish and next start included), the CLI, and
   the migration. Retire the engine's Stop on the dashboard in the same
   slice, since a stop must become a pause before anything restarts
   workers.
2. The dashboard: the status line, Pause, Stop and Resume at the three
   levels, Start sprint, Run next for tasks that may run, "Needed by" and
   "Waiting · FOR-65", the engine row and menu removed, "no worker" with
   Start worker. The design README and drawing change with it.
3. Before relying on restarts: a test that a worker killed hard (SIGKILL)
   leaves no agent process running. Then the supervisor, and the Workers
   view.
