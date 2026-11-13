# STATUS

Current snapshot only. History up to 2026-09-08 (sprints 1 to 54) is in
`docs/checkpoints/status-history-through-2026-09-08.md`.

## Where the project is (2026-11-13)

- Driving document: `docs/reviews/2026-11-10-full-review-and-finish-plan.md`
  (full review of engine, runner, dashboard, frontend and UX, with a six-phase
  plan, 0 to 5).
- Phases 0 to 3 are done: sprints 55 (baseline and host safety), 56 (engine
  truthfulness) and 57 (structure) are closed and archived under
  `docs/sprints/archive/`.
- Active sprint: **sprint 58 — frontend rebuild** (`docs/sprints/current.md`),
  Phase 4 of the plan. The dashboard is rebuilt to
  `docs/design/dashboard-v7/` (ADR-0020). Every page of the design exists,
  and everything the old dashboard could do has a place or is dropped on
  purpose (`docs/design/dashboard-v7/legacy-capabilities.md`). What remains
  of the sprint is the closing checkpoint.
- Nineteen tasks of the sprint were run by Foreman itself. On
  2026-11-13 the owner asked for the engine to be stopped and the rest done
  by hand; it has been since. What the engine did well and badly is in
  `docs/sprints/current.md` and the defects are in `docs/sprints/backlog.md`.
- `main` is pushed to `origin/main`. Work happens on short branches from
  `main`; the operator checkout stays off `main` (the `_integration` worktree
  holds it).
- Schema version 23. 1334 Python tests, 356 frontend tests. The built bundle
  is not in git; `foreman dashboard` builds it when it is missing or stale.
- In the Foreman project's own database FOR-38 still reads "in progress":
  its work was merged by hand and there is no command to say so.

## What sprint 56 changed for an operator

- A cancelled task is never written to or merged by the engine; a blocker
  signal stops the workflow; a crash between steps costs one step.
- Completion evidence states facts tied to the branch head (tests, review,
  judged criteria) and has no score (ADR-0018).
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
review, human gate, deferred approval, merge). Still true: agents run with full permissions as the engine's user
(sandboxing is Phase 5), and there is no login.

## Operating decisions (owner, 2026-11-10)

- Claude drives the work. Whether a slice runs by hand or through Foreman is
  decided per slice; cost and safety observations from Foreman runs are
  recorded in the sprint doc.
- No identity provider or notification channel is being chosen now. Login and
  notification stay pluggable seams for adopters to fill.
- Codex stays in the tree but is treated as experimental until it has a
  shipped role, cost accounting and a real-binary smoke test.

## Documented conflicts between spec, mockup and code

- Shipped workflows test before review and gate the merge behind a
  policy-governed human gate; spec §5 shows review first.
- `_builtin:mark_done` terminates a workflow with no outbound transition.
- Events require a run and a task, so project-level events attach to a
  synthetic system run on one project task.
- Spec §6.2 says that in autonomous mode the orchestrator does not create a
  branch and the agent reports its own. The engine creates the branch and
  worktree in both modes (ADR-0012, amended 2026-11-11); the agent names the
  task, not the place it works in.
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

- `./venv/bin/python -m unittest discover -s tests` (1334 tests)
- `npm --prefix frontend run lint`, `npm --prefix frontend test` (356 tests) and `npm --prefix frontend run build`
- `ruff check foreman tests scripts` (pyflakes and syntax rules)
- `./venv/bin/python scripts/validate_repo_memory.py`
- CI runs all of the above; its Python job builds the frontend first, since
  the bundle is not in git (`.github/workflows/ci.yml`).
- The look: `scripts/dashboard_shot.mjs` against the rules in
  `docs/TESTING.md` ("Checking the look").
