# STATUS history through 2026-11-26

The 'Where the project is' section of `docs/STATUS.md` as it stood on
2026-11-26, moved here when Foreman began writing `docs/STATUS.md` from its
database (ADR-0040, sprint 65). What still holds as a standing fact is also in
`docs/guide/`: `assay-project.md`, `closing-a-task-by-hand.md`,
`backend-layers.md` and `branches-and-the-operator-checkout.md`. Earlier
history (sprints 1 to 54) is in `status-history-through-2026-09-08.md`.

## Where the project was (2026-11-26)

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
- **2026-11-25.** Sprint 62 (finish what's there) is finished; its ten
  tasks, FOR-50 to FOR-59, ran through Foreman. The roadmap now takes
  stage 3 (a method for the agents) before stage 2. The method, the
  repository layout and the rules for parallel work are decided in
  ADR-0040; the workflow and role model they need, and what each step is
  given, in ADR-0041. The next sprint builds ADR-0040's build order through
  Foreman. Until each item lands, the rules in `AGENTS.md` still hold.
- **2026-11-25, after sprint 63.** Every command a Claude Code step runs
  has `/dev/null` as standard input, through Claude Code's shell prefix
  (`fix/runner-commands-get-no-stdin`), so the 18-minute stall of FOR-53
  cannot recur there. `merge_approval` and `sprint_completion` stay `auto`
  for Foreman's own project, at the owner's word.
- **2026-11-26.** ADR-0043 (the work is paused, not the engine) is
  accepted and built by hand (`feat/holds-pause-and-block`): Pause, Stop,
  Resume and Block on a task, a sprint or the workspace, the status line of
  a sprint's work, and the engine off the page. Left for later: a
  supervisor that keeps workers running, and a Workers view (ADR-0043
  "Order of work", part 3).
- **2026-11-26, sprint 65 opened** (`docs/sprints/current.md`): ADR-0040's
  build items 4 to 6 and the rule for moving up a role's models, through
  Foreman. The open items of `docs/sprints/backlog.md` are in Foreman's
  backlog as FOR-73 to FOR-91.
- Nineteen tasks of sprint 58 were run by Foreman itself. On 2026-11-13 the
  owner asked for the engine to be stopped and the rest done by hand; it has
  been stopped since. What the engine did well and badly is in the archived
  sprint file and the defects are in `docs/sprints/backlog.md`.
- `main` is pushed to `origin/main`. Work happens on short branches from
  `main`; the operator checkout stays off `main` (the `_integration` worktree
  holds it).
- Schema version 31 (31: a user's holds, ADR-0043; 30: a run's record,
  ADR-0042; 29: an event belongs to a run, a sprint or the project,
  ADR-0037). 1681 Python tests, 533
  frontend tests (2026-11-24). The built bundle
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
