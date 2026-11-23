# STATUS

Current snapshot only. History up to 2026-09-08 (sprints 1 to 54) is in
`docs/checkpoints/status-history-through-2026-09-08.md`.

## Where the project is (2026-11-20)

- Driving document: `docs/reviews/2026-11-10-full-review-and-finish-plan.md`
  (full review of engine, runner, dashboard, frontend and UX, with a six-phase
  plan, 0 to 5).
- Phases 0 to 4 are done: sprints 55 (baseline and host safety), 56 (engine
  truthfulness), 57 (structure) and 58 (frontend rebuild) are closed and
  archived under `docs/sprints/archive/`.
- Sprint 58 closed on 2026-11-15
  (`docs/checkpoints/2026-11-15-sprint-58-closed.md`): the dashboard is the
  one in `docs/design/dashboard-v7/` (ADR-0020), and everything the old
  dashboard could do has a place or is dropped on purpose
  (`docs/design/dashboard-v7/legacy-capabilities.md`). The Phase 4 items
  that were not built are in `docs/sprints/backlog.md`.
- Sprint 59 (the engine can be left running again), the first of Phase 5,
  closed on 2026-11-16 (`docs/checkpoints/2026-11-16-sprint-59-closed.md`):
  the engine defects found during sprint 58 are fixed, the agent sandbox has
  its first cut (ADR-0023), and three dashboard follow-ups landed. The
  engine fixes are covered by tests and have not been seen in a run of the
  engine.
- Sprint 60 (what is there works and makes sense) closed on 2026-11-19
  (`docs/checkpoints/2026-11-19-sprint-60-closed.md`).
- **The roadmap from 2026-11-19** is at the top of `docs/ROADMAP.md`: nine
  stages, from the core proven to memory. The decisions about the manager
  and people are in `docs/sprints/backlog.md`.
- Sprint 61 (the core, proven; stage 1 of the roadmap) closed on
  2026-11-20 (`docs/checkpoints/2026-11-20-sprint-61-closed.md`). Assay's
  sprint 2 ran through Foreman with nobody stepping in: 8 of 8 merged, 7
  first time. No sprint is open. The next one is stage 2, and it starts
  with an ADR for the identity system inside Foreman
  (`docs/sprints/current.md`).
- Nineteen tasks of sprint 58 were run by Foreman itself. On 2026-11-13 the
  owner asked for the engine to be stopped and the rest done by hand; it has
  been stopped since. What the engine did well and badly is in the archived
  sprint file and the defects are in `docs/sprints/backlog.md`.
- `main` is pushed to `origin/main`. Work happens on short branches from
  `main`; the operator checkout stays off `main` (the `_integration` worktree
  holds it).
- Schema version 28. 1622 Python tests, 487 frontend tests (2026-11-23). The built bundle
  is not in git; `foreman dashboard` builds it when it is missing or stale.
- Foreman's own project in its database is clean (2026-11-18). Sprint 60c is
  completed: FOR-42 is closed as already done (its work was in `main` at
  `721d877`), and FOR-49 was brought up to date with `main` by hand and
  merged at `de26c2d`. No Foreman task is open, and the 57 merged remote
  branches are deleted.
- **Assay** (`../assay`) is the first outside project run through Foreman.
  Its sprints 1 and 2 are merged and completed. Its merges are approved by
  Foreman (`merge_approval=auto`, owner, 2026-11-20).
  - Its `main` is pushed to its GitLab at `d64947e` (owner, 2026-11-23),
    sprints 1 and 2 included.
  - Its tests write JUnit reports (unittest-xml-reporting), and its
    `test_command` is `python -m xmlrunner discover -s tests -o
    "$FOREMAN_TEST_REPORT_DIR"` (ADR-0035).
  - Its engine (`foreman serve assay`) and its API
    (`192.168.50.107:8090`, `scripts/assay-api status`, from the Assay
    checkout) do not restart after a reboot. Both have been down since the
    reboot of 2026-11-23.
- A task whose work was finished outside the engine is closed with
  `foreman task done <id> --reason ...` (Mark done in the task's More menu);
  `foreman task reopen` undoes it. FOR-38 was closed that way.
- **The backend is laid out in layers** (ADR-0032, slice 14 of
  `docs/sprints/current.md`, owner, 2026-11-19). `.importlinter` states the
  stack and CI holds it, with no exception. It landed in five branches that
  changed no behaviour. Every module path changed: a branch opened before
  2026-11-19 must be rebased, and a process started before then must be
  restarted. Every change the CLI and the services make goes through
  `foreman.mutations` (`tests/test_layers.py`). The five longest modules are
  packages split by concern. Left, in ADR-0032: the CLI's reads are its own,
  and seven functions are over 200 lines.

## What sprint 56 changed for an operator

- A cancelled task is never written to or merged by the engine; a blocker
  signal stops the workflow; a crash between steps costs one step.
- Completion evidence states facts tied to the branch head (tests, review,
  and the criteria an approving review covers) and has no score (ADR-0018).
  The criteria judge was removed on 2026-11-19.
- Guidance written for a task reaches its next agent step and shows as
  waiting or read.
- Retries continue the interrupted session; a quota stop needs the CLI's
  own notice or wording; a pause survives an engine restart; `foreman run`
  answers engine commands; a crash of `foreman serve` exits non-zero.
- Autonomous mode works inside a per-task worktree and degrades, not
  blocks, when the agent does not name its task.
- The database refuses statuses and types outside the vocabulary.

## Running unattended

Sprint 55 closed the six host and money risks the 2026-11-10 review
reproduced: browser routes into the API (ADR-0016), API control over shell
commands, paths and role permissions (ADR-0017), unbounded per-run spend,
agents outliving the engine, the lease loss that re-ran the developer, and
approve/deny executing outside the engine lock (ADR-0011 amendment). None of
this was exercised by one real engine run (FOR-13, 2026-11-10: develop, test,
review, human gate, deferred approval, merge). Sprint 59 narrowed what an agent is handed (ADR-0023): a role's tool
allowlist is passed to the CLI, the reading reviewers have three tools, and
an agent process no longer gets the engine's environment or the operator's
MCP connectors. Still true: the process runs as the engine's user with a
shell and the network (a container per task is later in Phase 5), and there
is no login.

## Operating decisions (owner, 2026-11-10)

- Claude drives the work. Whether a slice runs by hand or through Foreman is
  decided per slice; cost and safety observations from Foreman runs are
  recorded in the sprint doc.
- No notification channel is being chosen now. On identity the owner
  decided on 2026-11-19 that Foreman gets a simple identity system of its
  own (roadmap stage 2), which a company-wide one can replace later. This
  supersedes the 2026-11-16 line that no login or user work was planned.
- Codex stays in the tree but is treated as experimental until it has a
  shipped role, cost accounting and a real-binary smoke test.

## Documented conflicts between spec, mockup and code

- Spec 6.4 (a finished sprint is tagged, with a note where asked) was
  half built until sprint 62, slice 2 (ADR-0036). What the spec leaves open
  is decided there:
  - a taken tag name gets `-2`;
  - the tag is pushed where merges are;
  - a failure leaves the sprint finished and says why.

- Spec 6.3 says an *autonomous* project has its sprints finished by the
  engine. Since 2026-11-19 (owner) that is the project setting
  `sprint_completion` ("Finish sprints: A user / Foreman"); the autonomy
  level no longer decides it (ADR-0025 amendment).

- Design v7 draws every board column open, and an empty one says "None". On
  the dashboard a column folds to a narrow strip showing its name, read
  downwards, and its count; the count is gold when a task in it needs you.
  An empty column starts folded, and a person's own fold or open is
  remembered per project in their browser (owner, 2026-11-18: a long workflow
  made the board unreadable). The design's open columns share the row's
  width; on the dashboard every open column is 272px wide, as Trello's lists
  are, and the board scrolls sideways past the page (owner, 2026-11-18).
  The board is 160px taller than the room left in the window below where it
  starts (owner's choice in the board lab, 2026-11-18). A column with more
  cards scrolls them under its heading, and an edge where columns are cut
  off fades out. The design draws the board growing with its tallest column.
  Each column is a panel, with its cards one step lighter
  (`--color-panel-item`). The drawings show no column panels; the design
  README's rule for panels was revised to include them (below). A column's
  scrollbar sits in the panel's margin.
- The design README's "Look" was revised by the owner on 2026-11-18. A
  tinted panel now holds a group of things one may act on: Needs you, the
  decision, a board column, a manager's proposal. Before, the tinted
  surface meant "act here", and only Needs you and the decision had it.
  The proposal card lost its outline and is a panel. The manager side bar
  has the page's ground instead of the bar tone, so a panel in it shows. Every scrollbar in the
  app, the page's own included, is thin and grey. The drawings were not
  redrawn: they show the outlined proposal card and the browser's
  scrollbars. This is the same feature as Jira's open request
  JRACLOUD-85706, and Trello, YouTrack and Linear have it.
- Design v7 keeps gold for "needs you" and the primary decision. Controls
  that open more in place ("Show all", "More details", "Finished sprints",
  "Earlier") are gold too since 2026-11-17 (owner: one look for all of
  them, grey or gold; gold chosen because text is in both greys). One
  token, `--color-expander`, sets it.
- Design v7 draws Edit and More beside a task's title, and in "Needs you"
  a button only on approve-merge rows, with the fourth kind named
  "unblock". Since ADR-0030 (owner, 2026-11-17) the title also has the
  state's button (Run next, Stop or Reopen) and Close, More holds only
  Block, Split and Delete, and a blocked task's row reads "Blocked", says
  why, and has Unblock.
- Design v7 draws the line between "Needs you" rows stopping short of the
  tinted surface's edges. The dashboard runs it edge to edge, like every
  other list (owner, 2026-11-17).
- Design v7's `05-task-overview.html` shows the manager's side bar on a
  task page. Since ADR-0029 (owner, 2026-11-17) the side bar on a task is
  the conversation with the task's agents; the screen is not redrawn.
- Shipped workflows test before review and gate the merge behind a
  policy-governed human gate; spec §5 shows review first.
- `_builtin:mark_done` terminates a workflow with no outbound transition.
- Events require a run and a task, so project-level events attach to a
  synthetic system run on one project task.
- Spec §6.2 says that in autonomous mode the orchestrator does not create a
  branch and the agent reports its own. The engine creates the branch and
  worktree in both modes (ADR-0012, amended 2026-11-11); the agent names the
  task, not the place it works in.
- Spec §6.3 revised 2026-11-16 (ADR-0025): the engine completes a resolved
  sprint only in an autonomous project; in a directed or supervised one the
  sprint stays active until a person finishes it. Implemented in
  `SprintFlow.resolve`; `engine.sprint_ready` now means "resolved, waiting for
  a person".
- Spec §6.4 sprint checkpoints (tag, note, event) are not built.
- ADR-0007 described a restricted planner session that was never built; the
  manager chat was a full-access Claude Code session that changed project
  state itself, against the design's "it proposes changes; nothing happens
  until the person confirms". ADR-0022 (2026-11-13) supersedes ADR-0007: the
  manager proposes (`foreman proposal create`), a person confirms in the side
  bar or with `foreman proposal confirm`, and the CLI refuses every other
  state change inside a manager session. The session still has a shell, so
  this is enforced at the CLI boundary, not sandboxed.
- `AGENTS.md` named `docs/mockups/foreman-mockup-v6.html` as the UI
  authority. On 2026-11-12 the owner agreed a new design and said it was
  ready for implementation; `docs/design/dashboard-v7/` is now the UI
  reference (ADR-0020) and the mockup is kept as history. The old application
  was removed on 2026-11-12 by owner decision (ADR-0020, decision 11);
  `/dashboard/legacy` is not found.
  `docs/design/dashboard-v7/legacy-capabilities.md` lists what it could do
  and where each thing is now.
- The running dashboard differs from the design's drawings where the owner
  corrected it on 2026-11-13 (ADR-0020, Amendments): the backlog is a page of
  its own, reached from a button beside Project settings, not a third tab;
  the breadcrumb has no "Workspace" step; planned sprints are reordered with
  earlier and later buttons, not by dragging. The design README states the
  first of these; the drawings were not redrawn.
- The design's Needs you has four kinds: accept filed work, approve a plan,
  approve a merge, unblock. Pending decision gates (a proposed sprint order)
  are a fifth kind the design does not show. Resolved: the needs-you endpoint
  carries them as `settle_order`, so they appear in Needs you on the
  workspace and project pages ("Settle sprint order", with Accept and
  Reject), settled with `PATCH /api/v1/gates/{id}`. The design README still
  names four kinds; revise it when product direction is next edited.
- Resolved (sprint 58 slice 3, ADR-0021): the design's backlog is a sprint
  row of kind `backlog` that is never listed or run as a sprint; the standing
  "Intake queue" sprint is gone (migration 21 moved its waiting work into the
  backlog). Accepted intake work and agent follow-ups now wait there until a
  person plans them into a sprint, on the backlog page.

## Validation baseline

- `./venv/bin/python -m unittest discover -s tests` (1622 tests)
- `npm --prefix frontend run lint`, `npm --prefix frontend test` (487 tests) and `npm --prefix frontend run build`
- `ruff check foreman tests scripts` (pyflakes and syntax rules)
- `lint-imports`: the layers contract in `.importlinter` (ADR-0032; needs
  Python 3.11, so CI runs it on the 3.12 job)
- `./venv/bin/python scripts/validate_repo_memory.py`
- CI runs all of the above; its Python job builds the frontend first, since
  the bundle is not in git (`.github/workflows/ci.yml`).
- The look: `scripts/dashboard_shot.mjs` against the rules in
  `docs/TESTING.md` ("Checking the look").
