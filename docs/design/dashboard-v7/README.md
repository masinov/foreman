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
| `02-project-sprints.html` | Project, Sprints tab: engine, needs you, the sprint queue |
| `03-project-backlog.html` | Project, Backlog tab: filed work, accepted work, plan into a sprint |
| `04-sprint-list.html` | Sprint, list view |
| `05-task-overview.html` | Task, Overview tab, with the manager side bar open |
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
- **Project** has three tabs of work: Sprints, Backlog, Activity. Its
  configuration is a separate page, **Project settings** (General and
  Workflow), reached from the title row. It is not a tab.
- **Sprint** shows its tasks as a list or a board (one column per workflow
  step, with Queued first and Done last).
- **Task** shows the pending decision first, then four tabs: Overview,
  Changes, Checks, Activity.
- **Manager** is one conversation per project. It is a side bar on the
  right of every page inside a project, toggled from the same place in the
  top bar, and it stays open as you move. It proposes changes; nothing
  happens until the person confirms.
- **Engine** is one per project. Its state and controls are on the project
  page; below project level they are in the top bar.
- **Needs you** is one list of four kinds of item: accept filed work,
  approve a plan, approve a merge, unblock. It appears at workspace level
  (all projects) and project level.
- **Work flows one way:** filed, accepted, planned into a sprint. The engine
  runs only the active sprint. A task an agent creates goes to the backlog.
- **History is one click away, not in the way.** The project shows the
  sprint queue (active, then planned in run order); finished sprints are a
  closed line that opens in place. A sprint shows all its tasks, done last.
- **Activity is one stream at three depths:** project shows milestones,
  sprint shows each finished step, task shows every run and its output.

## Look

| Token | Value |
|---|---|
| Ground | `#0c0c0e` |
| Bar and inset surface | `#101013` |
| Tinted surface (something to act on) | `#131317` |
| Selected | `#1b1b20` |
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
- **One tinted surface means "act here":** Needs you, and the decision on
  the task page. Nothing else is boxed.
- **Status** is a 6px dot and a word, never a pill.
- **Lists are capped:** Needs you 5, planned sprints 5, finished sprints 10,
  backlog 25, activity 25, each with a way to see the rest.
- **Width:** the page is at most 1200px wide and must work down to phone
  width without sideways scrolling of the page (tables may scroll inside
  their own container).

## Words

Plain words, no engine jargon on the page. "Needs you", "Who decides",
"A person" or "Foreman", "Fact" and "Claim". A fact is something the engine
measured; a claim is something an agent reported (ADR-0018). Empty states
say what is true and what happens next.

## Mark and motion

`16-identity-and-motion.html`. The mark is an F drawn as a task list with
one square, the task in hand. On the workspace page the top bar shows the
mark and the word; inside a project it shows the mark alone, and the square
breathes while that project's engine is running.

Something moves only when something is happening: the engine dot while it
runs, a thin line under a step in progress, placeholder rows if loading
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
