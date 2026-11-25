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

- **Done, the test count (`feat/test-report-count`, sprint 62 slice 1,
  ADR-0035):** read from the JUnit XML the test command writes into
  `FOREMAN_TEST_REPORT_DIR`. A step's records are saved as they happen, so
  the test step's start is when the tests started.
- **Done (sprint 62 slice 4, by Foreman, ADR-0038), facts that need the repository:** the files a step changed with
  their added and removed lines, and for a merge what it brought in, where
  main was before, and whether the branch was kept. Also "Session:
  continued from attempt 1", which today is only in the agent's command
  line.
- **Done, engine fixes found on the way:** records about a sprint or the
  engine are stored as the sprint's or the project's own, not pinned to a
  task (ADR-0037, sprint 62 slice 3). After it (owner, 2026-11-24): a
  task's Activity lists every record the engine kept on it, so it shows at
  least what its sprint's does; the worktree clean-ups are the project's;
  a sprint's Activity does not list the sprint's own records.

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
  - (Done on 2026-11-24, sprint 62 slice 5.) The project page's tabs with their controls on the tab line too (its
    Activity filters and New sprint are under it, in a heading of their
    own), so every tabbed page works the same;
  - small frictions seen on the way. Done on 2026-11-22: "Measured by
    Foreman", the APPROVE line, "Merged in 0.1 s", the review named by its
    role. Still to do: the lone "OK" a test's detail shows (with the test
    count). Spend written three ways: done 2026-11-24 (`ui/Spend`).

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
     - **Tiers, so a step does not wait for every test (owner,
       2026-11-24).** Today every task's test step runs the project's whole
       `test_command`, however small the change. The common practice:
       - at each step, only the tests the change can affect, picked by a
         tool that knows which tests run which code (coverage-based, such
         as pytest-testmon, or by the dependency graph, such as
         `vitest --changed` or Nx and Bazel "affected"). Groups kept by
         hand go stale and miss side effects;
       - before the merge, the whole suite, because `main` must always
         pass;
       - before a release or on a schedule, what is too slow for every
         merge (journeys through the interface).
       A suite then says which tier it belongs to, and the merge gate
       stays the full run.
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
   - **Survey done (2026-11-24),** of the company's own projects and of established practice.
     - **The kinds of check these projects need:**
       - fast unit tests (pytest or unittest);
       - tests against services, such as Postgres, Redis, a time-series store, or a client's database reached over VPN;
       - optimizer quality against reference results (objective value, feasibility, solve time on a fixed set of cases), often comparing two branches;
       - model training and evaluation against a baseline metric, often on a GPU;
       - GPU-only jobs;
       - evaluation of LLM output, which is paid and varies from run to run;
       - a CAD plugin on Windows with a licence and real drawing files;
       - long exact-solver and certificate runs;
       - image builds;
       - browser flows (several frontends and no browser tests yet).

       Two projects already split their tests into tiers of their own: one into free tests on every commit and paid model tests on request, another into unit, certificate, control and provenance tiers with a `slow` marker. Results are scattered: no common place for metrics or objective values.
     - **Practice:**
       - **Selection is an optimisation allowed to miss.** The tools that pick tests from a change are bound to one language or to a build graph (pytest-testmon, `vitest --changed`, Nx, Bazel), or predict from history (Meta, Develocity). The full required set still runs at the merge gate, on the merged result.
       - **CI tiers:** a fast set on each change, the full required set at merge, and slow, end-to-end, model and performance checks after merge, nightly or before release.
       - **Machines:** a job states labels (OS, GPU, licence, interactive desktop), and a runner advertises them (GitHub, GitLab, Buildkite).
       - **Results:** JUnit XML for test cases; metrics checked against a pinned baseline with a tolerance (pytest-benchmark, asv, MLflow evaluation, Evidently); files kept as evidence (screenshots, transcripts).
       - **Who owns what:** the project defines what runs, in its repository; the platform decides what is required and where it runs (protected config, runner pools).
       - **Agent- or person-performed checks** are workflow steps that record a verdict with evidence. There is no standard yet.
     - **Conclusion (Claude, for the owner to decide):** a tier is not a subsystem of its own. It is a verification step in a declarative workflow, as review tiers already are (`development_tiered`), and its parts land with the stages that own them:
       - **which command a test step runs:** today always the project's one `test_command`;
       - **a rule by changed paths:** small, and possible now;
       - **results as counts, metrics with a baseline and files:** the evidence model, ADR-0018;
       - **the machine it needs:** stage 6, labels;
       - **an agent-run check:** a tester role, stage 3;
       - **per-run services:** stage 4;
       - **slow checks on the integrated `main`:** stage 8;
       - **the tests view:** stage 5, designed with the other views.

       Language-bound test selection stays inside a project's own command (pytest-testmon or `--changed`), never in Foreman.
     - **2026-11-25:** the "rule by changed paths" is now part of ADR-0041: a workflow route may test the changed path groups a project names, so a test tier becomes a route to a test step.
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
       4);
     - open, not decided (owner, 2026-11-23):
       - a view of the code;
       - a view of the repository's history: branches, commits, merges and
         the tags of finished sprints.
   - **To settle for all of them at once:**
     - at which level each view lives (workspace, project, sprint, task);
     - what is a view of its own and what is a tab inside one;
     - how a view links to the others (from a test to its task, and from
       a task to the requirement it touches);
     - where the manager chat sits beside them;
     - how it all works on a phone.
   - **Already decided:**
     - the four levels;
     - one screen at a time.
   - **No longer a rule:** "no code browser" (2026-06-16). It came from
     seeing Foreman as working beside VS Code. Since 2026-09-03 and
     2026-11-19, Foreman is where the work is done: people specify, accept,
     supervise and correct, and VS Code is the occasional hands-on
     exception (owner, 2026-11-23).
   - **The order:** one design reference for the whole set comes first,
     then one view at a time, each from a mockup.
7. **How a project's repository is organised (owner, 2026-11-24).** Which
   documents a project keeps, where each lives, and who writes it when. This
   is for Foreman's own repository and, through `foreman init`, for every
   project it runs. The aims, in the owner's words:
   - standard, and good practice;
   - useful for robust development;
   - easy for agents to navigate, easy for users to find things in, and
     auditable;
   - without frictions and collisions.

   "Keep things tidy for now. Discussing the organization of the work
   requires care and online research."
   - **Decided 2026-11-25** after the research: ADR-0040 (with the
     proposal `docs/proposals/2026-11-24-method-repository-parallel-work.md`).
     The notes below are kept as the record.
   - **First raised** as finding 23 of the sprint 54 run
     (`docs/reviews/sprint-54-live-run-notes.md`, 2026-09-08), "major
     (structural)": the shared files every branch edits at the top collide
     whenever two branches overlap. It was not carried into this backlog
     then, and was raised again on 2026-11-24.
   - **The facts, 2026-11-24.** Merges, of the last 300, that touched each
     file:
     - `CHANGELOG.md` (one 140 KB file): 216;
     - `docs/STATUS.md`: 130;
     - `docs/sprints/current.md`: 130;
     - `docs/ARCHITECTURE.md` (986 lines): 88;
     - `docs/MANUAL.md` (2,015 lines): 73;
     - `docs/sprints/backlog.md`: 66;
     - the ADR index: 24.

     Folder sizes: `docs/prs/` 314 files (2.6 MB),
     `docs/sprints/archive/` 50, `docs/checkpoints/` 26.

     Two branches can both take the next ADR number. In sprint 62, FOR-50
     and FOR-52 each went back to develop once because of these files: a
     develop pass, a test run and a second approval each.
   - **A first sketch** (Claude, 2026-11-24; a starting point for the
     research, not a decision):
     - each fact has one home: what Foreman's database holds (sprints,
       backlog, status, what each task did) is not kept by hand in
       markdown, and any markdown copy is generated;
     - a task's branch touches only files about its own change;
     - logs are one file per entry: changelog fragments gathered at
       release, ADR numbers given at merge with a generated index;
     - `docs/prs/` becomes the task's own record;
     - the manual and the architecture split by topic;
     - `foreman init` sets the standard up.
   - **To research before deciding:**
     - how established projects and agent-driven repositories organise
       docs and agent instructions (AGENTS.md conventions, docs-as-code,
       Diátaxis);
     - changelog fragments (towncrier, changesets, scriv);
     - ADR practice (MADR, numbering at merge, generated indexes);
     - what auditors and users expect to find, and where;
     - what is regenerated, and when it is written (sprint finish,
       release).

8. **A code map for agents, surveyed in depth (owner, 2026-11-25).** What
   each step is given about the repository so that it starts in the right
   place without reading its way through (ADR-0041 sets the three layers:
   project, task, step). The owner likes the idea of a generated map of the
   code, as Aider's "repo map" does (symbols from tree-sitter, ranked by how
   much they are referenced). It likely pays more as a codebase grows. "Worth
   a deep research on tools like this so 1: we can borrow from what already
   exists ... and 2: we design a truly robust system that saves time AND
   tokens. But we can save that for later, since nothing depends on it
   strictly."
   - **To survey:** Aider's repo map, code indexes (ctags, tree-sitter tags,
     LSP, Sourcegraph's SCIP), the search agents already do, and published
     comparisons of indexes against plain search.
   - **Measure first:** reads before the first edit and tokens per step,
     which Foreman can count from the tool calls it records (ADR-0041), so
     the survey can be judged on this repository and Assay.

9. **Which models and harnesses run which work, configured by the user
   (owner, 2026-11-25).** One ladder per role ("cheap, then strong") is too
   simple. A user should be able to define combinations they have found
   work for kinds of task, for example Kimi for frontend work, DeepSeek for
   backend work, Fable or Astra for hard mathematics, with their own tiers
   and handoffs. "Let the user play with it and configure what they
   empirically determine works best for their workflows", rather than a
   fixed "hard or easy", "long or short" tier. For the future.
   - **A runner profile, not a model.** Harness (Claude Code, Codex, later
     others), model, endpoint and its settings (an Anthropic-compatible
     endpoint through `[agent.env]` already works) and effort. A ladder is
     an ordered list of profiles.
   - **Which ladder, chosen by the same fixed facts as routes** (ADR-0041):
     a label the project defines, the task type, a changed path group
     (known after develop; before it, from the planner's expected files).
     First matching rule wins, and a rule without facts is the default. No
     free expressions, so every choice can be explained: "Develop runs on
     Kimi: label frontend".
   - **A handoff across harnesses cannot resume a session.** The next rung
     starts fresh from the step's declared inputs: the task, the records
     (the report, the findings) and the change so far (ADR-0041 section 5).
     Step records are what make this possible.
   - **Each profile must pass what Foreman relies on:** records, the
     completion marker, commands without standard input, the sandbox, cost
     reporting. A profile that cannot is refused when it is saved.
   - **Empirical by design:** `foreman outcomes` per rule and profile (cost,
     send-backs, time, failures), so a user sees what works. Later Foreman
     could suggest a change to a rule from those numbers.
   - **Per provider:** keys passed to the agent by name, quotas and prices
     tracked separately.
   - Builds on today's decision on moving up after failures (below, "Large
     tasks ran on the default model"), which works the same with one ladder.

## Found while reviewing sprint 63 (2026-11-25)

Sprint 63 ran unsupervised, and its own reviews approved in seconds. Claude
then had each task reviewed against its criteria. The faults that would bite
at once were fixed before the code went live:
- `fix/sandbox-git-and-prune`;
- `fix/records-robustness`;
- `fix/stdin-claims`.

These are left:
- ~~Commands that read standard input still hang when they hold a
  heredoc.~~ Fixed on 2026-11-25 (`fix/runner-commands-get-no-stdin`): every
  Claude Code command runs through a shell prefix with `< /dev/null`,
  checked live with the owner's approval. Codex is still not verified.
- **Whether `AGENTS.md` reaches the agent once is a guess about Claude
  Code's loading.**
  - Foreman checks `repo_path/CLAUDE.md`, but the agent runs in a worktree
    under `<repo>/.foreman/worktrees/`, and Claude Code walks every ancestor
    folder. It probably loads the main checkout's `CLAUDE.md` and
    `AGENTS.md` too: twice, and possibly an older copy.
  - Where there is no `CLAUDE.md`, the load relies on a built-in plugin
    (`cc-plugin-agents-md`).
  - Settle it with Claude Code's debug output from a real worktree.
- **Reads before the first edit are miscounted in places** (FOR-63):
  - Codex commands are counted twice (`agent.command` and the
    `commandExecution` tool use);
  - a `>` inside quotes counts as a write;
  - newlines do not separate commands;
  - `python3 - <<'EOF' ... open(p,'w')` and `git apply`/`mv`/`cp`/`rm` are not
    seen as changes.
- **The sandbox (FOR-64):**
  - `run_scope = "none"` is not enforced;
  - pushes are deterred, not prevented or detected;
  - a sandbox left by a hard-killed engine is removed only by prune;
  - the reviewer in Assay's sandbox has Bash next to its linked `.env` (the
    app's own login; `.env.admin` is not linked).
- **Records (FOR-61, FOR-62):**
  - a verdict's criteria entries are not compared with the task's own list;
  - a project's own reviewer that uses `{previous_output}` now sees only the
    developer's words outside the record.
- **Large tasks ran on the default model.** FOR-61, FOR-62 and FOR-64 were
  marked large, but no role has a model ladder, so `complexity` changed
  nothing. **Decided with the owner, 2026-11-25** (a sprint 64 candidate;
  the rule goes into ADR-0041 with it):
  - **The size label goes.** `complexity` only chose the ladder's first
    rung, and it is a guess ("a bit... ambiguous"). It leaves model choice,
    the task forms, the planner's output and the dashboard.
  - **A person or the manager pins a model per task and step** with the
    override that already exists (`executor_overrides.models`, the task
    page's overrides).
  - **A step moves up a rung only after failures of its own work:** the
    review sent it back with an S1 or S2 finding, the tests failed after
    it, or the agent could not finish. Not on an engine restart, a branch
    brought up to date after a conflict, a wait for usage limits, or an
    infrastructure error. Today every visit to the step counts
    (`workflow_runner/base.py`), so a conflict send-back climbs the
    ladder too.
  - **A role says how many failures on one rung before moving up**
    (`escalate_after`, default 2), so the cheaper model gets one more pass
    with the review's findings. Past the top rung, the task blocks for a
    person (later, ADR-0041's question to a person).
  - **Every move up is in the Activity with its reason**, and `foreman
    outcomes` compares cost and send-backs per model.

## Found while running sprint 62 through Foreman (2026-11-24)

- **Several tasks at once in one project.** The engine runs one task at a
  time (ADR-0039). Real parallelism, several agents each in its own working
  copy, is a separate decision with its own answer to shared files (owner
  direction 7) and to the machine's capacity. Owner: "Either sequential or
  parallel".
- **A branch is not brought up to date when its working copy is dirty.**
  `refresh_task_branch` skips the update without a record when the task's
  worktree has uncommitted changes, which happens when a develop step was
  cut off (FOR-56, after an engine restart). The merge step's conflict
  catches it later. Record the skip, or update once the interrupted work is
  saved.
- **Agents stall on commands that wait for input.** FOR-53's agent ran a bare
  `python3 -`, which waits for input, and sat for 18 minutes. Seen once;
  watch for it again before changing the runner.
- **Test tiers and a parallel suite** are owner direction 5 and the
  engineering list: the test step took 5 to 12 minutes on every pass, the
  largest part of each task's time.

## Left to finish the current product (checked against the code, 2026-11-23)

What is still open before roadmap stage 2. Each item was checked against
`main` at `d8cebac`. The lists this replaces are in
`docs/sprints/archive/backlog-lists-through-2026-11-23.md`. The design pass
under way is in the sections at the top of this file and is not repeated
here.

**Where the product does not hold together yet:**

- (Done in sprint 62, slice 2, ADR-0036.) Spec §6.4: a finished sprint is
  tagged, with a note where the project asks for one.
- (Out of date, found 2026-11-24.) Who finishes a sprint has its control:
  Settings › General › Finish sprints (`sprint_completion`).
- (Done in sprint 62, slice 6.) `foreman init` and Settings › Runners
  read the shipped roles and workflows only, not the workspace's or the
  project's own (ADR-0024).
- **"This machine" settings are read-only on the page.** That covers the
  working copies, their set-up command, linked paths, context folder, push
  remote and extra variables. The page names the `foreman config` command.
  Decide whether that is the rule or a gap.
- ~~**Manager replies are plain text.**~~ Done (sprint 62 slice 6): a finished reply is formatted; one still arriving and your own messages stay plain.
- **Earlier proposals are shown in full,** with no one-line summary (FOR-43).
  A send-back already names where the task goes.
- ~~**A task filed by an agent does not say which task the agent was working
  on.**~~ Done (sprint 62 slice 6): Overview and `foreman task show` say it.
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

- ~~**A running task's page opens two event streams,** the project's and the
  sprint's. One is enough.~~ Done in sprint 62 (`fix/task-a-running-task-s-page-uses-one-event-stream`).
- **No browser tests for the current dashboard.** `tests/test_e2e.py` was
  written for the old one (it checks that "the task page is not built"), and
  it is skipped here because Playwright is not installed. What is missing is
  a pack for the user's journeys: approve a merge, send back, pause, recover
  from an engine failure. It connects to owner direction 5.
- **The Python suite runs one test at a time** (1,636 tests, about 4½
  minutes). Running it in parallel (pytest with pytest-xdist runs the
  existing unittest tests as they are) could bring it to about a minute on
  this machine. First check that no tests share state: a fixed port, a
  shared temporary path, the process environment (owner, 2026-11-24).
- **No types in the frontend** (no TypeScript, no JSDoc types).
- **The store still repairs known schema drift every time it opens**
  (`_repair_known_schema_drift`). Migrations are not a deploy step.
- **The database is in the repository's folder** (`.foreman.db`).
- **The sprint stream polls SQLite every 500 ms.** It works; an in-process
  bus would let it wake on a write. Low urgency.
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
- `resume_human_gate` and `_run_leased_task` each sit in their own module
  of the orchestrator package; sprint 61 found that was all the item
  needed;
- a task's priority and size can be edited (sprint 59).
- **Decided against:** Python `Enum` classes for statuses (sprint 61).
