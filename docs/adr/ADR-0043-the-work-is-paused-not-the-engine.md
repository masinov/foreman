# ADR-0043: The Work Is Paused, Not The Engine

- **Status:** proposed (owner, 2026-11-25: "Go with it"; 2026-11-26, on
  the model below: "Perfect. I do think so")
- **Date:** 2026-11-26
- **Amends:** ADR-0011 (the command table's vocabulary and "a paused
  engine"), ADR-0039 (a paused task does not hold the queue; a request to
  run a task does not pass a pause or a block), ADR-0025's amendment on
  finishing sprints (Foreman does not finish or start a sprint that a
  pause or a block holds)

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
  pool the owner has asked for (backlog, owner direction 1), a per-project
  on/off for "the program" means nothing.

The owner and Claude compared three models as trees of actions and
outcomes: today's, one switch per project, and a pause at the level of the
work. The owner chose the third. Drafts of it tried a pause that is
inherited from sprint to task, with exceptions for a task resumed under a
paused sprint. The owner found it "weird", and a survey of other products
(Alternatives) found no product that lets one item run while its parent is
paused. Two patterns exist:

- **The parent wins, and both must be released:** a paused Windows print
  queue does not print a resumed job, CUPS holds a printer's jobs,
  Temporal needs a workflow and its activity both unpaused, Prefect and
  Airflow leave runs waiting under a paused pool or workflow, Buildkite
  shows a paused queue's note on every build it holds.
- **Pause all is a bulk action, and there is no parent state:** a torrent
  client pauses every torrent, and any one can then be resumed.

The owner chose the second for Pause, and asked for a true parent hold
beside it ("a 'Lock' button that is a true parent action"), which is Block
at every level. A second opinion (Fable 5.2, 2026-11-25) shaped Stop and
the storage, and found that a paused sprint still finished and started the
next one. The owner answered that (2026-11-26): "Pause should pause the
task and everything downstream that depends on it", and Foreman should
finish and start sprints itself "unless they have been deliberately
blocked".

## Decision

### 1. Two holds: Pause and Block

| | Pause | Block |
|---|---|---|
| What it is | a soft hold, on tasks only | a hard hold, with a reason, on a task, a sprint or the workspace |
| On a sprint or the workspace | pauses each unfinished task under it, as one bulk action; the sprint or workspace has no paused state of its own | one hold on the sprint or the workspace itself; nothing under it runs |
| A task under it | can be resumed on its own | cannot be resumed: its Resume is disabled and reads "Sprint blocked" or "Workspace blocked", with the reason on hover |
| Lifted by | Resume, on the task or on any level above it | Unblock, only where it was set |
| In Needs you | no | yes, with its reason |
| For | "hold this for now, I'll look" | "nothing here runs until I say", and parking for days |

- **Resume on a sprint** resumes its paused tasks. **Resume all** resumes
  every paused task in the workspace. Neither touches a block.
- **Unblock lifts only the block.** Tasks a user paused one by one stay
  paused: a block never erases a user's own pauses.
- **A task planned into a sprint joins paused** when every other unfinished
  task of that sprint is paused, so a sprint that reads "Paused" stays
  paused when work is added to it.
- **A project has no hold of its own.** It has one active sprint, so a
  project hold would be the sprint's under another name. When several
  sprints of a project can run at once, the project page shows each one's.

Where the controls are: the task page header; the sprint page header (the
project page header and the top bar show the active sprint's); the
workspace page header ("Pause all", "Resume all", "Block all").

### 2. A hold holds what comes after

A hold holds the thing held and everything downstream of it: whatever
cannot start until it is done (owner, 2026-11-26). Downstream is the
dependency chain that already exists:

- **a task's next step,** built-in steps included (tests, Merge, Mark
  done), so a held task never becomes Done;
- **the tasks that wait for it** ("Waits for", set on a task before it
  starts; `foreman/engine/selection.py`). They wait until it is done, so
  they wait through its hold;
- **the sprint's finish,** which waits for every task in it;
- **the next sprint's start,** which waits for that finish.

A blocked sprint is neither finished nor followed by the next one either,
even when its work is all done ("Blocked · ready to finish"). So Foreman
finishes and starts sprints by itself, where the project lets it
(`sprint_completion = auto`), unless a hold stops it: a task that is not
done, a blocked sprint, a blocked workspace.

Tasks of the same sprint that do not wait for a held task go on: a task's
hold holds only that task and what depends on it.

### 3. Holding now, and holding after the step

- **Pause and Block let a running step finish.** Then the hold applies.
  Nothing is cut.
- **Stop cuts the running step now,** and pauses what it was pressed on (a
  task; on a sprint or the workspace, each unfinished task under it, as
  Pause does).
  - Offered only while a step is running in what it would stop.
  - An agent step's process group is ended and its run settled as killed,
    as today. A test run's process is ended the same way.
  - A merge is never cut: cutting it half way is worse than waiting for it.
    It finishes, then the hold applies.
  - The status line reads "Stopping · Develop" until the run is settled,
    and "Stopped" only after.
  - The step runs again from its start on Resume. The cut visit is not
    counted against the step's visit limit, as with `steer_task` (ADR-0011,
    2026-11-16): a user cut it, it did not fail.
  - Stop is a red button and asks for no confirmation, because what it cuts
    is one step and that step runs again.
- **A hold lasts until a user lifts it.** A restart, a reboot or a crashed
  worker does not lift it.

### 4. Every button does something

- **Pause** is offered where something unpaused could run; **Resume** where
  something is paused; **Stop** where a step is running; **Block** where
  nothing is blocked at that level; **Unblock** where it is.
- **A task under a block offers no Resume or Run next that would do
  nothing:** they are shown disabled with "Sprint blocked" or "Workspace
  blocked". That is the one disabled control in the model, and the user
  chose it by blocking.
- **Resume asks no confirmation; its toast says what it resumed,** by key:
  "Resumed FOR-66 and FOR-67." Past three keys it says "and 4 more".
  Resuming is undone by pausing again, so a question before it would only
  be friction (owner, 2026-11-25).
- **Block asks for its reason,** as a task's Block does today; the reason is
  required.

### 5. What the other actions do

- **Start sprint** replaces "Activate sprint". It is how a user starts a
  sprint; Foreman starts the next one itself only as §2 says.
- **Run next** puts a task that may run first in line. A paused task shows
  Resume instead, never both: one button per intent. A `run_task` request
  for a task that is held when the worker takes it up is rejected, saying
  so; ADR-0039's rule 5, that a request to run a named task passes over a
  task waiting for a decision, does not pass over a hold.
- **Stop on a task leaves it paused, not blocked.** A task a user stopped
  is not in Needs you. Blocked is what Foreman says when it needs a user
  (a failure, a loop limit, a branch violation) and what a user sets with
  a reason.
- **Block on a running task** lets its step finish, then blocks it. Today
  Block exists only for a task that has not started.
- **A paused or blocked task does not hold the queue** (amends ADR-0039,
  which lets only a task waiting for a decision hold it). The sprint goes
  on with the tasks that do not wait for it; after a Stop that is seconds
  later. When the task is resumed it is first in line, and its branch is
  refreshed from the default branch before its next step, as any task's
  is (ADR-0012). A task held at a gate is the same: holding it releases
  the queue, and the collisions ADR-0039 removed are possible for that
  task, as they already are for a blocked one.
- **A decision made while held is recorded and waits.** Approving a merge
  of a paused task moves it to Merge, which runs on Resume: "Approved
  FOR-51. It merges on Resume." A held task waiting for a decision stays in
  Needs you, and its Status reads "Paused · Approval".

### 6. What the page says

**No name in a status line, a toast or a button.** A sprint's or a
project's title is free text of any length; these places are fixed and
short. They use fixed words, task keys, dates and times. Which sprint, who
acted, the reason and the full time are on hover; at phone width a tap on
the status line shows them.

One status line for a sprint, the same wherever it is shown (the sprint
header, the project header, the top bar, a row of the workspace's projects
table). When more than one is true, the first in this list wins:

- "Blocked · 14:02", "Blocked · 24 Nov" after the day it was set
  (the reason on hover)
- "Blocked · workspace"
- "Stopping · Develop"
- "Pausing · Develop finishing" (Stop stays offered, for a step taking
  too long)
- "Stopped · 14:02" (hover: the step that runs again)
- "Paused · 14:02": every unfinished task is paused
- "Working · FOR-65 Develop", with "· 3 paused" after it when some are
- "3 paused": nothing runs, and some tasks are paused
- "Ready to finish", "Blocked · ready to finish"
- "Not started"

**A worker fault stands beside the line, not in its place:** "Paused ·
14:02 · no worker". The user sees both that the work is held and that no
program could run it.

**A task's Status** keeps its existing shape: "Paused · Develop", "Blocked ·
Develop", with who, when and the reason on hover. "Waiting · Develop"
(another task is running) keeps its meaning; a task that waits for another
reads "Waiting · FOR-65". "Stopped · Develop" now means a user stopped it.

**A task shows what waits for it:** beside "Depends on", its Overview lists
"Needed by", so a user sees what holding it will hold.

### 7. The engine leaves the page

The Engine row on the project page, the engine menu in the top bar, the
engine's Start, Pause and Stop, and the word "engine" leave the dashboard.
The program that runs the work is called a **worker**.

- **While no worker holds a project,** the status line carries "no
  worker", with **Start worker**. That is the one worker control on the
  page. It is a fault to fix, not a switch for the work, and holds are
  untouched by it.
- **A supervisor will keep workers running** (a systemd user unit per
  project, restarting with a growing wait; a separate slice). With it,
  "no worker" appears only after its restarts have given up, and the
  button reads Restart.
- **A Workers view** in workspace settings (which workers are alive, idle
  or on which task, and their restart) comes with the supervisor or with
  the machine pool, whichever is first.
- **The command line keeps worker control:** `foreman serve` starts one and
  `foreman engine shutdown` ends one. Ending a worker holds nothing:
  another worker, or the supervisor, carries on with the work.
- **A crashed worker's run is settled by the next worker** (crash recovery,
  as today). Until then a "Pausing" or "Stopping" line stays, with "no
  worker" beside it.

### 8. How it is stored, and how the worker hears it

A hold is state that every page shows, not a message to a program, so it
is a row, not a command.

- **A pause is on the task:** `paused_at`, `paused_by`, and `pause_mode`
  (`finish_step`, `now`) on `tasks` (a migration). A sprint's Pause, Stop
  and Resume, and the workspace's, write these fields on each unfinished
  task in one transaction. There is no sprint or workspace pause to store.
- **A block on a task stays what it is:** status `blocked` with
  `blocked_reason`. A block on a sprint or the workspace is a row in a
  `holds` table: `scope` (`sprint`, `workspace`), `scope_id` (the fixed id
  `workspace` for the workspace, never null, so the unique index on
  `(scope, scope_id)` holds), `project_id` (null for the workspace),
  `reason`, `set_by`, `set_at`. Unblock deletes the row. Each Pause,
  Resume, Block and Unblock is also an event, which is the history.
- **A task is held** when it is paused, or blocked, or its sprint or the
  workspace has a `holds` row. One function, `is_held`, answers it for the
  API, the pages and the worker, with the reason.
- **Holds do not outlive what they describe.** A task's pause is cleared
  when it moves to another sprint or the backlog, is closed, or is
  reopened. A sprint's block row is deleted when the sprint is finished or
  cancelled.
- **The worker reads them where it reads commands today:** before each
  step, on every tick of an agent step (ADR-0011's poll sites), and, for
  Stop, while a test run waits. Before a step, a held task is parked: it
  stays where it is and releases its lease. A pause with mode `now` cuts the
  running agent step or test run; one with mode `finish_step`, and every
  block, wait for the step to end.
- **Choosing a task skips every held task,** and finishing a sprint or
  starting the next checks the sprint's and the workspace's holds first
  (§2). When nothing may run, the pass ends with the stop reason `held`,
  and a resident worker waits on `data_version` as it does now.
- **The command table keeps what is a message to a worker:** `run_task`,
  `steer_task` and `shutdown`. `pause`, `resume` and `stop_task` are
  retired. The API and the CLI write holds instead:
  `foreman pause <project> --sprint S | --task T [--now]`,
  `foreman pause --all [--now]`, `foreman resume` with the same choices,
  `foreman block <project> --sprint S "reason"`,
  `foreman block --all "reason"`, and `foreman unblock` with the same
  choices; `foreman task block` and `unblock` stay for a task. Run next
  queues `run_task` in the same transaction that checks the task is not
  held.
- **Existing state is carried over.**
  - A project whose engine stands paused, or was last stopped with the
    engine's Stop (which `engine_is_paused` reads as not paused), gets each
    unfinished task of its active sprint paused, mode `finish_step`, by
    whoever did it.
  - A task blocked as "Stopped by …" becomes a paused task: `in_progress`
    at its step, no blocked reason, paused by that user.

## Consequences

- **One way to start work:** start a sprint; after that Foreman carries on
  from sprint to sprint where the project lets it. **Two ways to hold it:**
  Pause, soft and per task, and Block, hard and with a reason, at the
  level meant. What depends on a held thing waits too.
- **No hidden or dead Resume,** except under a block a user set, where it
  is disabled with the reason.
- **A user's stop is never lost to a restart,** because it is a pause and
  pauses outlive programs. This is why the engine's Stop goes before a
  supervisor comes: today a supervisor would restart a stopped engine and
  carry on with the work.
- **Pause is slower than it was.** It waits for the running step, which may
  take many minutes. The status line says "Pausing" with the step, and Stop
  stays offered meanwhile.
- **Resume on a sprint resumes tasks a user paused one by one,** as a
  torrent client's Resume all does. A task meant to stay held is blocked.
- **A held task's branch can fall behind** while the sprint goes on. The
  refresh before its next step merges the default branch in; a conflict is
  handled by the workflow as for an unblocked task.
- **Every program shares holds through the database only,** which is the
  product's premise (ADR-0011): a dashboard on another host, the CLI, the
  intake API and every worker read the same rows.
- **Dependencies stay within a sprint.** "Waits for" names tasks of the
  same sprint, and sprints follow each other in queue order. That is all §2
  needs. Dependencies across sprints are in the backlog (owner direction
  10), for when sprints can run side by side.
- **The design changes** (`docs/design/dashboard-v7/README.md`): the Engine
  bullet becomes the status line and the controls of §1; "Activate"
  becomes "Start sprint"; the task Status bullet gains who held it and
  "Waiting · FOR-65"; the Overview gains "Needed by"; Needs you gains a
  blocked sprint and a blocked workspace; the toast for an approval of a
  paused task; "the engine dot" in Mark and motion becomes "the status dot
  while something is working". The drawing `02-project-sprints.html` loses
  its engine row.

## Alternatives considered

- **Keep the engine as the switch.** Rejected for the reasons in Context:
  two switches for one job, a Pause and a Stop that differ only for the
  program, and no meaning once a project has several workers.
- **One switch per project, no sprint or task hold.** Simple, but a user
  cannot hold one task to look at it while the others go on, and with
  parallel workers inspecting one task would halt all of them.
- **A sprint pause inherited by its tasks, with a task's Resume as an
  exception under it** (the drafts of 2026-11-25). It needed a rule for
  which level wins, exceptions shown on the sprint, and storage ordered by
  specificity. The owner found resuming a task inside a paused sprint
  "weird", and no product surveyed does it. Pause as a bulk action gives
  the same reach with no parent state.
- **The parent always wins, for Pause too** (print queues, CUPS, Temporal,
  Prefect, Airflow, Buildkite). Rejected for Pause: a task's Resume would
  do nothing under a paused sprint, which is the failure Microsoft's
  support pages for print queues describe. Kept for Block, where the user
  asks for exactly that and the reason is shown, as Buildkite shows a
  paused queue's note on every build it holds.
- **Resume on a sprint resumes only tasks paused by the sprint's Pause.**
  Rejected: it needs the sprint to remember which pauses were its own, a
  hidden state; parking a task is what Block is for.
- **Pause cuts the step, as today.** Rejected: the common wish is "let it
  finish, then hold", and cutting throws away a step's work. Stop is there
  for the urgent case.
- **A hold on the project.** Redundant while a project has one active
  sprint; the project page shows the sprint's controls instead.
- **Keep pause as commands in `engine_commands`.** Rejected: a command is
  addressed to a program and expires with it (ADR-0011 rejects a pending
  `pause` when a new engine starts), while a hold must outlive programs and
  be visible on every page.

Surveyed on 2026-11-26:
[Windows print jobs](https://msdn.microsoft.com/en-us/library/ms584322.aspx),
[CUPS](https://man7.org/linux/man-pages/man8/cupsenable.8.html),
[Temporal workflow pause](https://docs.temporal.io/encyclopedia/workflow/workflow-pause),
[Temporal activity pause](https://docs.temporal.io/activity-operations/pause),
[Prefect work pools](https://docs.prefect.io/concepts/work-pools),
[Airflow trigger on a paused DAG](https://docs.arenadata.io/en/ADO/current/airflow-cli/dags-trigger.html),
[Buildkite queues](https://buildkite.com/docs/clusters/manage-queues),
[qBittorrent "Resume all"](https://forum.qbittorrent.org/viewtopic.php?p=19882).

## Order of work

1. The task pause fields, the `holds` table, `is_held`, the worker reading
   them (built-in steps and the sprint's finish and next start included),
   the CLI, and the migration. Retire the engine's Stop on the dashboard
   in the same slice, since a stop must become a pause before anything
   restarts workers.
2. The dashboard: the status line, Pause, Stop, Resume, Block and Unblock
   at the three levels, Start sprint, Run next for tasks that may run,
   "Needed by" and "Waiting · FOR-65", blocked sprints and the workspace in
   Needs you, the engine row and menu removed, "no worker" with Start
   worker. The design README and drawing change with it.
3. Before relying on restarts: a test that a worker killed hard (SIGKILL)
   leaves no agent process running. Then the supervisor, and the Workers
   view.
