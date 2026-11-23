# Backlog

## A task's Activity, step by step (owner, 2026-11-22)

From a review of every step of ASS-10 and ASS-16 as a user, and a second
review that saw only screenshots. The mockup the owner chose:
https://claude.ai/artifact/5XgyCnzgX7QyeVFCJMj2we (one kind of line, the
step's facts beside it, the prompt as the first line).

- **Done, the step panel (`feat/task-step-panel`).**
- **Done, the table (`feat/task-steps-table`):**
  - only the task's own steps;
  - "attempt 2", "Committed" and "Approved by setting";
  - the commit on Test, Review and Merge rows.

  Still to do: the test count ("Passed · 186 tests") needs Foreman to
  record how many tests ran.
- **Then, facts that need the repository:** the files a step changed with
  their added and removed lines, and for a merge what it brought in, where
  main was before, and whether the branch was kept. Also "Session:
  continued from attempt 1", which today is only in the agent's command
  line.
- **Then, engine fixes found on the way:**
  - "Ran the tests" is recorded when the tests end, not when they start.
  - Records about a sprint or the engine (`engine.sprint_ready`, sprint
    finished, engine shut down) are pinned to a task through a made-up
    run, because every event must belong to a run and a task. Store them as
    what they are (an ADR first), say on the sprint that it is ready to
    finish, and list it in the project's Activity.

## The sprint page, step by step (owner, 2026-11-21)

The owner asked for the sprint page to be redesigned a little at a time,
from a mockup first, so less goes wrong at once. "When a user clicks on a
sprint, what should they see first?"

- **Done, the top (`feat/sprint-page-top`):** the title row; the goal,
  four lines then "Show all", beside Details (state, tasks, spend); two
  tabs, Tasks and Activity, each with its controls on the tab line (Add
  from backlog, New task, List | Board; By and All | Problems). Activity is
  the log alone. By names the role, the model on hover, on every activity
  list and on a task's Steps. The outcome line is off the sprint and
  project pages (ADR-0034 amendment).
- **Statistics view (owner):** how well agents do over many sprints, as
  numbers and graphs: first-time passes, send-backs by cause, a user's
  part, cost per merged task, time to merge, by role and model. The data
  is `GET /projects/{id}/outcomes`; where the view lives is decided with
  the other views (owner direction 6).
- **Proposed next, one at a time, each from a mockup:**
  - (Done on 2026-11-22, in the task's step panel: the prompt is the
    step's first line, and one button downloads the transcript.)
  - the project page's tabs with their controls on the tab line too (its
    Activity filters and New sprint are under it, in a heading of their
    own), so every tabbed page works the same;
  - small frictions seen on the way. Done on 2026-11-22: "Measured by
    Foreman", the APPROVE line, "Merged in 0.1 s", the review named by its
    role. Still to do: the lone "OK" a test's detail shows (with the test
    count), and spend written three ways.

## Activity, one stream at three depths (owner, 2026-11-21)

Built in three slices the same day, then redesigned after the owner's
review: rows of two and three lines, too much for a summary, titles full on
one page and cut on another, and a project list that mixed sprints, tasks
and the engine ("I want you to notice these things by yourself"). The
design that replaced it (`feat/activity-one-row`):

- **One row shape for every activity list**
  (`frontend/src/pages/shared/ActivityTable.jsx`): When · (Project) ·
  Subject · What happened · By · (numbers). One line per row, the same
  column widths on every page; the subject (key, then title) is cut with
  "…" at the same width everywhere, all of it on hover; why (a reviewer's
  reason, a failure, a person's reason) is on hover and on the page the
  row leads to, never under the row. At phone width the project, who and
  the numbers give way; what happened stays.
- **Each level lists its own things:** workspace Recent and project
  Activity, sprints (planned, started, finished) and the engine (stopped,
  paused, resumed, died); sprint Activity, each task's development, tests,
  review, a person's decision, merge, block, close or cancel, with a
  Problems filter (`GET /sprints/{id}/activity`); task Activity, every run,
  with the reason above the picked run's output. A sprint-level phrase
  names its step ("Tests passed", "Sent back", "Merged"), so there is no
  step column.
- **Left out:** bookkeeping runs, gates decided by the project setting, a
  running engine (the engine row says it), a merge's numbers (the outcome
  line says how the work went).
- **Everywhere:** "Activity" as the title, "Earlier" for more, day and time,
  lists that read again while the page is open (`usePagedList` follows the
  page's refresh), and the outcome line as one short sentence.
- **After the owner's second look (same day):** the engine's every state
  change is listed, starts included, so a stop never follows a stop (the
  owner: the rule must be solid, not special to some stops); the sprint's
  Activity has a Key column, as its task list does, and the project's a
  sprint-name column; the headings no longer repeat the tab ("Sprints and
  engine", "Runs"); "user", not "person", wherever the page or the CLI
  names someone (owner).
- **Not done:** a user's name on a decision at a gate, or on an engine
  stopped by a signal (neither records who; stage 2 identity will).

## Owner decisions, 2026-11-19: the manager and people (roadmap stage 2)

Settled in discussion with the owner on 2026-11-19. Stage 2 of
`docs/ROADMAP.md` builds them, after an ADR.

- **Work is registered.** Everything done through Foreman is listed and
  auditable; no task or feature is developed without being listed. The
  record is kept whole where code enters `main` (only Foreman's merge moves
  it), not by limiting sessions.
- **Identity.** Foreman gets a simple identity system of its own, which a
  company-wide one can replace later. This supersedes the 2026-11-16 line
  "no login, user or role-of-person work until the owner asks".
- **The manager** is the project lead and the person's way of operating
  Foreman. It sees everything and investigates freely (scripts, queries,
  tests run against `main`). It acts directly when a person asks, recorded
  under that person's name; a plan of several tasks is shown before it is
  applied. It writes no code that goes into the product: code comes only
  from tasks. It can adjust how a task is done: per-task model and policy
  overrides, notes to the developer and reviewers, the workflow before the
  task starts, engine control. The FOR-42 write limit (ADR-0022 amendment)
  is revisited with it.
- **One manager conversation per person per project.** What it does lands in
  the project's shared activity. There is no conversation owned by no one.
- **Roles:** owner (at least one per project; controls everything in it) and
  member. A client is a task's reporter, not a user.
- **Two decisions per task:** who is responsible, and whether it is accepted
  (or declined, or changed in type and accepted). They are independent: a
  ticket can name its responsible person and still be declined by them. A
  task runs only when it is accepted and has a responsible person.
  - A member filing their own work: responsible and accepted at once.
  - A member may file work for others to pick up; they are its reporter.
  - An owner may assign anyone; the person is notified.
  - A task with nobody responsible: any member or owner decides; whoever
    accepts it becomes responsible, unless an owner names someone.
  - A task from an external system waits; a connector may name the
    responsible person when that person is in the project.
  - Derived work (an agent's follow-up, a split) inherits the responsible
    person of the work it came from.
  - A person's manager acts as that person, with their rights.
- **Handing over:** offered and accepted between members; an owner reassigns
  directly; a person who leaves the project hands back to the owners.
- **Notices** go to the responsible person and always to owners, who also
  see what is waiting, on whom and since when, and can act.
- **Conflicts:** a change to someone else's work is a request to its
  responsible person or an owner (the proposal card, used for this). A
  change based on an out-of-date task is refused, saying what changed and
  by whom. Code conflicts stay with the merge.
- **Permissions:** a worker's freedom depends on the machine and what it can
  reach. Gates sit at the boundaries (entering `main`, shared or production
  resources, deploying) as policies with defaults a project can change.
- **Deferred:** decisions sent back to a ticketing app (owner: "let's not try
  to close absolutely everything right now").

## Owner directions, 2026-11-18: after sprint 60 and the base work

Recorded so they are not lost. Each one gets an ADR before any code. Sprint
60 and the remaining base work come first. Feature 1 is the next line of
work after that.

What they serve: Foreman as a software factory and a meta-harness. It
coordinates several harnesses and models, each with its own strengths and
prices. Its many thin arms work through existing tools (CI/CD, clusters,
trackers, identity) rather than rebuilding them. Before each arm's ADR,
survey the existing tools.

Base work that this framing makes necessary:

- **Outcome numbers per project, model and role:** first-pass success,
  send-backs, interventions by a person, and cost per merged task. These
  show whether routing between models pays.
- **Codex as a real second harness:** a smoke test against the real
  program, its cost recorded, and the same kind of task run through both
  harnesses.

1. **One central Foreman server, with workers on other machines.**
   - A worker program on each machine connects out to the server, keeps a
     clone per project and a working copy per task, and runs agent and test
     steps there. It streams events back and pushes the task's branch.
   - A project or step names a machine, or states requirements such as OS
     and installed software. A task stays on the machine that holds its
     agent session.
   - The setting is multi-user and multi-project, and identity is needed.
   - First case: a BricsCAD MCP server developed on a Windows machine.
2. **Shared compute, through a cluster manager, only when configured.**
   Foreman does not manage shared GPUs and CPUs: the company's people use
   them too. A project can point Foreman at a cluster manager, such as Ray,
   and a task's agent or a workflow step then submits jobs with resource
   requests. Foreman records each job on the task (waiting, where, how
   long, log, result) and enforces limits on it.
3. **Releases and deployment, through existing CI/CD.** Foreman does not
   build or deploy. It decides when a version is cut, under a policy gate
   such as merge approval. It starts the CI/CD pipeline (GitLab CI, GitHub
   Actions, and so on), follows it, and shows its stages, artifacts and
   environments on the sprint. It reacts to a failure. The same connector
   reads CI checks on a task's branch, which is the pull-request
   integration of Phase 5. A release can be code, an image or a trained
   model; in each case Foreman records where it came from.
4. **Workflows above the task: a sprint workflow (owner's question,
   2026-11-18; leads into 3).**
   - **Today:** workflows are per task only. A sprint's life is fixed in
     code (`foreman/engine/sprints.py`, ADR-0025): activated, its tasks run,
     finished by a person or by the engine. A run must belong to a task.
   - **The idea:** a declarative sprint workflow with steps before its tasks
     (plan, plan gate) and after them. After them come checks on the
     integrated `main`, a release gate, the release pipeline, its
     observation, and notes.
   - **The loop it allows:** a failing sprint-level check files fix tasks
     into the same sprint, and the sprint runs again until its checks pass.
     No task workflow can express that.
   - **Global roles (owner, 2026-11-18):** roles triggered at the end of a
     sprint that look at the whole sprint, not at one task. This is where a
     judge of the sprint's acceptance belongs; the per-task criteria judge
     was removed (ADR-0010 amendment).
   - **Further out:** recurring and event-triggered loops at project level,
     which create tasks or sprints and stop there.
   - **Seen in a real run (2026-11-20, Assay sprint 2).** All eight tasks
     merged, but Assay's `docs/ROADMAP.md` still lists S2 as not delivered,
     because none of the tasks was asked to update it. Closing a sprint's
     records is a step after its tasks, and only a sprint workflow can
     express it. Owner: "A friction noted in favor of the suggestion i made
     before."
5. **Tests that are designed, not only watched (owner, 2026-11-22 and
   23).** Who decides what must be tested, how it runs, and whether the
   requirement is met. The owner's examples:
   - a test must exist for one function of a component;
   - a test runs the app's full workflow through the interface and returns
     a screenshot of the end screen.
   - **Today:**
     - Each project has one shell command (`test_command`). Foreman keeps
       its exit code, duration, commit and output. It does not know which
       tests ran: a count, a name or a failure is only in the printed text.
     - Nothing says what must be tested. A task's acceptance criteria come
       nearest, and a review checks them, not a test.
     - There is no tester role. Tests are written only if the developer
       decides to.
     - The Checks tab has an "Evidence files" section, but the server
       always sends it empty.
   - **One place per project, a Tests view, with three parts:**
     - **What must be tested.** Written by a user, or proposed by the
       manager and accepted by a user (Foreman stores it). Each one has the
       behavior, its level (unit, component, or a journey through the
       interface) and what proves it, such as a passing test or a
       screenshot. It either blocks a merge or only advises.
     - **Suites, how tests run.** Kept in a TOML file in the project's
       repository, like CI configuration, so they stay in step with the
       code and an agent changes them through review. Each suite has:
       - its command and its report (JUnit XML is common to pytest,
         vitest, jest, Playwright and others);
       - what it needs (a journey starts the app, waits until it is ready,
         then drives a browser);
       - what it produces (results, screenshots);
       - when it runs: every task, tasks touching some files, before a
         merge, or on a schedule.
     - **Coverage, each requirement against reality.** Whether a test
       exists, which one, its last result and its screenshot. A requirement
       with no test is a gap. Closing a gap is a task for a tester role,
       and the review checks that the test really proves the requirement.
   - **On a task:**
     - the Checks tab shows the requirements the task touched and whether
       their tests passed;
     - the tests that failed come first, then the tests the task added or
       changed, then the full list, folded, with a search;
     - a test's own name and docstring say what it checks (a fact); a
       model's summary is a claim (ADR-0018);
     - a journey's screenshot fills Evidence files.
   - **Over time, in the statistics view:** flaky, slow and skipped tests.
   - **Survey before the ADR:**
     - Playwright and its reports;
     - how test tools and CI pick tests (pytest markers, vitest projects,
       "affected" in Nx or Bazel);
     - tools that track coverage against requirements;
     - whether the central server's workers run tests through an existing
       CI runner (direction 3).
6. **The views, thought through as one system (owner, 2026-11-23).**
   The owner has proposed several views over time. Before any one of them
   is built, they are designed together: roadmap stage 5, the left bar.
   - **The views proposed so far:**
     - board and sprints;
     - backlog;
     - activity;
     - statistics (agents over many sprints);
     - tests (direction 5);
     - docs, from which the spec editor may grow. The spec editor may also
       be its own app that talks to Foreman;
     - resources;
     - people and the manager (roadmap stage 2);
     - settings;
     - at workspace level: projects, shared roles and workflows, machines
       (direction 1);
     - on the sprint: its workflow's checks and releases (directions 3 and
       4).
   - **To settle for all of them at once:**
     - at which level each view lives (workspace, project, sprint, task);
     - what is a view of its own and what is a tab inside one;
     - how a view links to the others (from a test to its task, and from
       a task to the requirement it touches);
     - where the manager chat sits beside them;
     - how it all works on a phone.
   - **Already decided:**
     - the four levels;
     - one screen at a time;
     - no code browser (owner, 2026-06-16).
   - **The order:** one design reference for the whole set comes first,
     then one view at a time, each from a mockup.


## Left to finish the current product (checked against the code, 2026-11-23)

What is still open before roadmap stage 2. Each item was checked against
`main` at `d8cebac`. The lists this replaces are in
`docs/sprints/archive/backlog-lists-through-2026-11-23.md`. The design pass
under way is in the sections at the top of this file and is not repeated
here.

**Where the product does not hold together yet:**

- **Spec §6.4 is half built.** A completed sprint is marked completed, but
  the repository is not tagged, no checkpoint note is written and no
  `engine.checkpoint` event is recorded. The `write_checkpoint_notes`
  setting exists and does nothing.
- **Who finishes a sprint** (`autonomy_level`, ADR-0025) has no control in
  the dashboard; it is set from a terminal.
- **`foreman init` and Settings › Runners read the shipped roles and
  workflows only**, not the workspace's or the project's own (ADR-0024).
- **"This machine" settings are read-only on the page.** That covers the
  working copies, their set-up command, linked paths, context folder, push
  remote and extra variables. The page names the `foreman config` command.
  Decide whether that is the rule or a gap.
- **Manager replies are plain text.** Task descriptions and reviews are
  formatted.
- **Earlier proposals are shown in full,** with no one-line summary (FOR-43).
  A send-back already names where the task goes.
- **A task filed by an agent does not say which task the agent was working
  on.** The event records it (`filed_from_task_id`); no page shows it.
- **A task cannot move from one sprint to another directly.** It goes back
  to the backlog and is added again.
- **Codex records its cost as 0** (`foreman/runner/codex.py`).
- **Runs, prompts and events are kept forever** unless a project sets
  `run_retention_days`, `prompt_retention_days` or `event_retention_days`.

**Safety for work filed by other systems (ADR-0028), not built:**

- a limit per day for a project whose standing sprint is fed by intake;
- a cap on how many tasks one agent step may file, and refusing a filing
  that repeats an open or declined task;
- trust per access token.

**Engineering:**

- **A running task's page opens two event streams,** the project's and the
  sprint's. One is enough.
- **No browser tests for the current dashboard.** `tests/test_e2e.py` was
  written for the old one (it checks that "the task page is not built"), and
  it is skipped here because Playwright is not installed. What is missing is
  a pack for the user's journeys: approve a merge, send back, pause, recover
  from an engine failure. It connects to owner direction 5.
- **No types in the frontend** (no TypeScript, no JSDoc types).
- **The store still repairs known schema drift every time it opens**
  (`_repair_known_schema_drift`). Migrations are not a deploy step.
- **The database is in the repository's folder** (`.foreman.db`).
- **The sprint stream polls SQLite every 500 ms.** It works; an in-process
  bus would let it wake on a write. Low urgency.
- **`resume_human_gate` and `_run_leased_task`** have their own modules
  (`foreman/engine/orchestrator/gates.py`, `tasks.py`) but are still
  methods of the orchestrator class.
- **No motion for live data** (a row arriving, a step finishing).

**For a later roadmap stage, kept so nothing is lost:**

- **Stage 2:**
  - sign-in and a user's name on every decision;
  - the manager's conversations per user, with a turn lock, a kill when
    the user disconnects, and a cost per turn;
  - notices by email or chat, and replying from them (today: webhooks
    only).
- **Stage 3:** a planner step per task, with criteria and a protected test
  written by someone other than the developer.
- **Stage 6 and the owner directions:**
  - parallel workers and a container per task (the sandbox's first cut is
    ADR-0023);
  - pull requests (no code opens one today);
  - Codex as a real second harness, with a smoke test;
  - multi-repository projects, a price table for other endpoints, budgets
    per day;
  - raw output capped and redacted in a table of its own, and records kept
    apart from telemetry;
  - response models on the API, and a deployment guide.

**Done since these were written** (checked on 2026-11-23):

- a finished sprint can be reopened (owner, 2026-11-18);
- `foreman role|workflow set --workspace` changes a workspace default;
- the test command is set in Settings;
- the "Developer (worker fleet)" role is gone;
- the criteria judge is removed (ADR-0010 amendment, 2026-11-19);
- a sprint opens on its List, and the board says how many cancelled tasks
  it leaves out;
- the task and sprint pages were looked at against real runs (Assay sprints
  1 and 2; ASS-10 and ASS-16 on 2026-11-22);
- the manager's conversation is kept in SQLite;
- a task's priority and size can be edited (sprint 59).
- **Decided against:** Python `Enum` classes for statuses (sprint 61).
