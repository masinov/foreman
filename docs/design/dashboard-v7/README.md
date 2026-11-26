# Dashboard design v7

The UI reference for the Foreman dashboard, agreed with the owner on
2026-11-12 (ADR-0020). It replaces `docs/mockups/foreman-mockup-v6.html` as
the authority for the dashboard's structure, wording and look.

Each file is one screen as a standalone page. Open it in a browser. The
pages are drawings: they show structure, wording and style with inline
styles. They are **not** markup to copy. The product is built from tokens,
primitives and class-based CSS (see ADR-0020).

Text in `[square brackets]` is a placeholder for a value the drawing did not
have. It is never a literal string to render.

## Screens

| File | Screen |
|---|---|
| `00-screen-map.html` | The four levels, what each page shows and does (text only) |
| `01-workspace.html` | Workspace: needs you across projects, projects, recent milestones |
| `02-project-sprints.html` | Project, Sprints tab: the work's status and controls, needs you, the sprint queue |
| `03-project-backlog.html` | The backlog (now a page of its own): filed work, accepted work, plan into a sprint |
| `04-sprint-list.html` | Sprint, list view |
| `05-task-overview.html` | Task, Overview tab, with the manager side bar open (superseded for the side bar: on a task it is the agents', ADR-0029) |
| `06-manager-open.html` | Project page with the manager side bar open |
| `07-sprint-board.html` | Sprint, board view |
| `08-project-settings-workflow.html` | Project settings, Workflow |
| `09-project-activity.html` | Project, Activity tab |
| `10-project-settings-general.html` | Project settings, General |
| `11-project-finished-sprints.html` | Project, Sprints tab with finished sprints open |
| `12-task-changes.html` | Task, Changes tab |
| `13-task-checks.html` | Task, Checks tab |
| `14-task-activity.html` | Task, Activity tab |
| `15-workspace-settings.html` | Workspace settings |
| `16-identity-and-motion.html` | The mark, top bar options, motion samples |

## Structure

Four levels, one page each, and a breadcrumb that says which you are on:
Workspace / Project / Sprint / Task.

- **Workspace** is the only place that spans projects. No manager here.
- **Project** has two tabs: Sprints and Activity. A tab changes what the
  page shows; it is never a place. As on every tabbed page, a tab's own
  controls (New sprint on Sprints, All | Sprints | Pauses and blocks | Worker on Activity) sit on
  the tab line at its right, never in a heading row under it; a heading stays
  only where it marks one group off from another (Sprints: "Active and
  planned" and "Finished", folded) (owner, 2026-11-24). The **Backlog** and **Project settings**
  (General and Workflow) are pages of their own, each with a breadcrumb step,
  reached from two buttons in the project's title row. (Revised 2026-11-13;
  `03-project-backlog.html` still draws the backlog as a tab and is kept for
  its content, not its placement.)
- **Sprint** has its goal (four lines, then "Show all") beside its
  details (state, tasks, spend), as a task's Overview sets what it is
  beside its facts, then two tabs: Tasks, as a list or a board (one column
  per workflow step, with Queued first and Done last), and Activity. A
  tab's own controls sit on the tab line at its right, never in a row of
  their own under it (owner, 2026-11-21).
- **Task** shows the pending decision first, then four tabs: Overview,
  Changes, Checks, Activity. Overview is the steps, the description and
  the acceptance criteria as filed (formatted), and every detail beside
  them at once. It has no checks summary and no "More details" (owner,
  2026-11-22): the Steps table and the Checks tab say it.
- **Manager** is one conversation per project. It is a side bar on the
  right of a project's pages and its sprints, toggled from the same place in
  the top bar, and it stays open as you move. It proposes changes; nothing
  happens until the person confirms. Its finished replies are
  formatted text; your own messages stay as typed.
- **Agent** is the same side bar on a task page (ADR-0029, owner
  2026-11-17): the conversation with the agents doing that task. Its steps
  in order, what each said and did, followed as a running step prints, what
  a person told them, and the box to tell the agent something. It is closed
  until the user opens it, and stays as the user left it, on every task and
  the next visit, remembered apart from the manager's (owner, 2026-11-24).
- **Work** (ADR-0043, owner 2026-11-26) replaces the engine on the page. A
  user holds the work, not a program. Its status line is one short line
  with no name in it, the same on the project page's Work row, the sprint's
  Details and title row, the top bar below project level (a menu; at phone
  width only its dot) and the workspace's projects table: "Working · FOR-65
  Develop · 1 paused", "Pausing · Develop finishing", "Stopping · Develop",
  "Paused · 14:02", "Stopped · 14:02", "2 paused", "Blocked · 14:02",
  "Blocked · workspace", "Ready to finish", "Waiting", "Not started", each
  with "· no worker" when no worker runs a project with work to do. Who, why
  and when are its detail: on hover, and on a tap.
  - **Pause** lets a running step finish, then nothing after it starts;
    **Stop** (the one red button) cuts the step, which runs again on
    Resume, and is offered only while a step runs; **Resume** lifts pauses.
    No question is asked before any of them; the toast names the tasks
    ("Resumed FOR-66 and FOR-67."). On a sprint or the workspace ("Pause
    all", "Stop all", "Resume all") they act on each task in it.
  - **Block** holds a task, a sprint or the workspace, with a reason, until
    Unblock where it was set. A sprint's Block is in its More; Unblock is
    beside its title. A task under a block shows a disabled "Sprint
    blocked" or "Workspace blocked" in place of Resume.
  - **Start worker** appears only beside "no worker": a fault to fix, not a
    switch for the work. **Start sprint** replaces Activate.
- **Needs you** is one list of four kinds of item: accept filed work,
  approve a plan, approve a merge, unblock. It appears at workspace level
  (all projects) and project level. Two more are about sprints, not
  tasks: settle a proposed sprint order, and finish a sprint whose every
  task is done or cancelled, where a user finishes sprints. That row has a
  Finish button (owner, 2026-11-24). A sprint a user blocked is one too
  ("Blocked sprint", its reason, Unblock; ADR-0043). The workspace's own
  block is lifted from above its projects (Unblock all).
- **Work flows one way:** filed, accepted, planned into a sprint. Foreman
  runs only the active sprint. A task an agent creates goes to the backlog.
- **History is one click away, not in the way.** The project shows the
  sprint queue (active, then planned in run order); finished sprints are a
  closed line that opens in place. A sprint shows all its tasks, done last.
- **Activity is one stream at three depths:** project shows its sprints,
  the pauses and blocks put on its work and the workspace's (ADR-0043), and
  its worker (started, stopped, died), sprint shows what
  happened to each of its tasks, task shows every run and its output. Every
  list is one table, one line per row, with the same columns (owner,
  2026-11-21; `frontend/src/pages/shared/ActivityTable.jsx`). By names the
  role ("Developer", "Code reviewer", "Foreman", a user); the model is on
  hover. A sprint's Activity filters by who (Everyone, each role, Foreman,
  Users) and by Problems. How well agents do over many sprints is a
  statistics view, not a line on these pages (owner, 2026-11-21).
- **A task's Status** (the sprint's task list and the task's Overview,
  owner 2026-11-24): what it is doing, and where it is under way the step,
  named as Activity and the board name it: "Running · Develop" while a step
  of it runs, "Blocked · Test"; "Waiting for merge approval", "Queued",
  "Done" and "Cancelled" as they are. A user's hold says so first
  (ADR-0043): "Pausing · Develop" and "Stopping · Develop" while the step
  still runs, then "Paused · Develop" or "Stopped · Develop", "Blocked" under
  a block on its sprint or the workspace, "Blocking · Develop" for a Block
  waiting for the step to end; who, when and why on hover. A task in
  progress waiting its turn is "Waiting · Develop" ("Foreman runs it after
  FOR-53", or "No worker runs this project.", on hover); one not started
  that waits for another, "Waiting · FOR-65". A "Run next" not started yet
  reads "Runs next · Develop" and its button is a disabled "Runs next". The
  task's Overview lists "Needed by" beside "Depends on": what holding it
  holds too. The task's Steps row says the
  same ("Waiting here", "Runs next", "Paused here") and why a step was returned to ("Waiting
  here · sent back: merge conflict", "· sent back by review", "· tests
  failed"); a gate's Attempts counts its pause and its decision as one. The
  board's columns are the stages. Elsewhere a step is named the same way
  ("Stopped at Test" in the decision box, "· at Test" in Needs you).
- **A confirmation is a toast** (owner, 2026-11-24): after an action, its
  success sentence passes in the bottom left corner of the window on every
  page for about six seconds (a live region; a new one replaces it; it stays
  while the pointer or focus is on it; a quiet close control), and never
  moves the page's content. At phone width it spans the bottom inside the
  gutter. An error stays inline where the action failed. An approval or a
  send-back is one sentence everywhere: "Approved FOR-51. Foreman goes on
  with Merge.", "Approved FOR-51. It goes on with Merge on Resume." (a task a
  user holds), "Approved FOR-51. It waits at Merge until a worker runs.",
  "Sent FOR-51 back to Develop."
- **An active sprint whose every task is done or cancelled** says so in
  State: "Ready to finish", with "Every task is done or cancelled." on
  hover and "Finish sprint" beside the title (ADR-0037).
- **A finished sprint's State** says which commit its tag marks (ADR-0036):
  "Finished 20 Nov at 6f79f4a", with the tag's name on hover; or "Finished
  20 Nov, not tagged", with why on hover. The note is not shown on the page.
- **The project's Activity** says "Finished" for a finished sprint, with
  "3 tasks merged, tagged checkpoint-… at 6f79f4a" on hover; or "Finished,
  not tagged" in the failure colour, with why on hover (ADR-0037).
- **The sprint's goal** shows as many lines as fit beside its Details
  (never fewer than four), then "Show all". Stacked on a phone, it keeps
  four.
- **A picked step has one shape for every kind of step** (owner,
  2026-11-22, from a mockup): on the left what happened, in order, each
  line a time, what happened in plain words, and what it ran, wrote or
  printed, beginning with "Sent the prompt" for an agent's step; on the
  right the step's facts (Result, Why, Decided by, After, Main before, the
  commit it was about, Session, Changed, Brought in, By, Model, May use,
  Took, Spend, Next; ADR-0038), each only where it
  applies, and one button, Download the transcript. No composed summary,
  no headings per kind of step, no JSON or event names, and nothing only
  one line has. A test step's result says how many tests ran when the
  test command reported them: "Passed · 1,599 tests, 1 skipped", "Failed ·
  3 of 186 tests" (ADR-0035), on Activity and on the Overview's Steps.
  The Checks tab's Tests detail is the sentence the step's log ends with,
  and names the tests that failed.
- **A run's story has one rule for long text** (owner, 2026-11-21): what
  someone wrote (an agent's message, a user's guidance or reason) is shown
  whole; code and what a program printed (a command the agent ran, a
  tool's result, test output, an error) show their first three lines, with
  "Show all" when there is more. Nothing is cut without a way to open it.

## Look

| Token | Value |
|---|---|
| Ground | `#0c0c0e` |
| Bar and inset surface | `#101013` |
| Panel (a group of things to act on) | `#131317` |
| Selected | `#1b1b20` |
| Item on a panel (a board card) | `#1b1b20`, its own token |
| Scrollbar thumb, and on hover | `#2e2e35`, `#4a4a52` |
| Text | `#dedcd8` |
| Secondary text | `#a3a19c` |
| Quiet text | `#85837e` |
| Gold (needs you, primary decision) | `#c9a55a`, outline `#6d5a2f` |
| Green (passed, approved) | `#6fbf9d` |
| Red (failed) | `#e08a8a` |
| Blue (running) | `#7fb4d2` |
| Structural line | `#26262b` |
| Table header line | `#2c2c33` |
| Row line inside a tinted surface | `#202026` |
| Row line | `#18181c` |
| Control border | `#34343a`, input `#2c2c32` |

- **Type:** Inter 13px for everything; Source Serif 4, 600, 21px for the
  page title only; JetBrains Mono 11.5px for keys, commits, paths and
  amounts. Section headings are 13px/600. Table headers are 11px quiet.
- **Controls:** 26px high (24px inside rows), radius 3px, 12px text. An
  approval in a list is an outlined gold button. The one filled gold button
  is the decision on the task page.
- **Lines have three weights** (see the table). Structural lines sit under
  the top bar, under a tab row and around the manager side bar. A table has
  one line under its column headers and faint lines between rows, none
  above the first row or below the last. Sections are separated by space.
- **A panel holds a group of things one may act on:** Needs you, the
  decision on the task page, each column of a sprint's board, a manager's
  proposal. It is the tinted tone with the 3px radius, and has no outline.
  A thing that sits on a panel as an object of its own (a board card) is
  one step lighter. What needs the person is said in gold, not by the
  panel. Nothing else is boxed: settings, tables, lists and activity are
  lines and space. (Revised by the owner on 2026-11-18. Before, the tinted
  surface meant "act here" and only Needs you and the decision had it.)
- **Scrollbars** are thin (8px), a grey thumb with no track, everywhere,
  the page's own included.
- **The manager side bar** has the page's ground, not the bar tone, so a
  panel in it reads as it does on the page. Its structural line sets it
  apart.
- **Status** is a 6px dot and a word, never a pill.
- **Lists are capped:** Needs you 5, planned sprints 5, finished sprints 10,
  backlog 25, activity 25, each with a way to see the rest.
- **Width:** the page is at most 1200px wide and must work down to phone
  width without sideways scrolling of the page (tables may scroll inside
  their own container).

## Words

Plain words, no engine jargon on the page. "Needs you", "Who decides",
"A user" or "Foreman" (owner, 2026-11-21: "user", not "person", wherever the page names someone), "Fact" and "Claim". A fact is something the engine
measured; a claim is something an agent reported (ADR-0018). Empty states
say what is true and what happens next.

## Mark and motion

`16-identity-and-motion.html`. The mark is an F drawn as a task list with
one square, the task in hand. On the workspace page the top bar shows the
mark and the word; inside a project it shows the mark alone, and the square
breathes while a step of that project's work runs.

Something moves only when something is happening: the status dot while a
step runs, a thin line under a step in progress, placeholder rows if loading
takes longer than 200 ms, a brief highlight when a task changes stage. All
motion is off under `prefers-reduced-motion`.

## What the drawings assume that the engine did not have on 2026-11-12

- A backlog that is not a sprint, with accept, decline and plan-into-sprint.
- Lists that page and filter on the server.
- A cross-project needs-you list and project milestones.
- The files changed by a task and their diff, served by the API.
- Evidence files (screenshots, recordings, traces). Phase 5; the screens say
  "none required".
- Identity. The top bar shows who is acting; until a provider is plugged in
  that is the name of the access token in use.

## Spend, written one way (owner, 2026-11-24)

An amount, and the tokens shown with it, is always in the mono number font, the amount first ("$0.09 · 3.5K tokens"); a zero is blank in a table column or a list row and "$0.00" in a details row or a heading. Every page writes it through `ui/Spend`.
