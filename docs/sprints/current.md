# Current Sprint

## Sprint 58 — frontend rebuild

- **Opened:** 2026-11-12, from Phase 4 of
  `docs/reviews/2026-11-10-full-review-and-finish-plan.md`
- **Status:** in_progress
- **Method:** the owner asked for Foreman to build this itself. Slices 1 to
  11 were filed as tasks in this repository's Foreman project and run by the
  engine, with Claude planning the tasks, reviewing each diff at the merge
  gate and correcting by hand. On 2026-11-13 the owner asked for the engine
  to be stopped ("this is getting utterly distracting"); everything since is
  by hand, on short branches.

### Goal

The dashboard is the one in `docs/design/dashboard-v7/` (ADR-0020): four
levels, one page each; the manager as a side bar; settings as their own
pages; a backlog; lists that page. The old frontend is gone.

### Constraints

- ADR-0020 is binding: source layout, routes, data hooks, class-based CSS
  from tokens, tests with each page. The bundle is not in git (decision 10).
- The old application was removed early by owner decision (decision 11);
  `legacy-capabilities.md` is the checklist of what it could do.
- API changes follow ADR-0019 (`/api/v1`, one error envelope) and keep the
  CLI and the dashboard on the same mutation service.
- Tasks do not edit `CHANGELOG.md` or this file (every branch touching the
  same lines conflicts at merge); the entry is added when the task lands.
- Page tests run in jsdom; the look is checked with
  `scripts/dashboard_shot.mjs` against the rules in `docs/TESTING.md`.

### Affected areas

`frontend/src/` (rewritten), `foreman/dashboard_frontend_dist` (rebuilt),
`foreman/dashboard/` routers and `foreman/dashboard_service.py` (new
endpoints), `foreman/mutations.py` and the store (backlog), tests on both
sides, `docs/`.

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 0 | Design reference in the repository, ADR-0020, pointers, sprint 57 archived | done | Claude | `docs/design/dashboard-v7/`, ADR-0020 |
| 1 | Frontend foundation: tokens, primitives, shell, router, API client and hooks, the workspace page | done | Foreman (FOR-17) | `frontend/src/` layout, workspace page |
| 2 | API: workspace overview, needs-you across projects, milestones, sprint paging | done | Foreman (FOR-18, FOR-20) | endpoints under `/api/v1` |
| 3 | Backlog: unplanned work has a place that is not a sprint | done | Foreman (FOR-19, FOR-21, FOR-22) | ADR-0021, migration 21, endpoints, CLI |
| 4 | Project page: engine, needs you, sprint queue, Activity tab | done | Foreman (FOR-23, FOR-34) | `pages/project/` |
| 5 | Backlog | done | Foreman (FOR-25), then Claude | a page of its own after owner review (ADR-0020, Amendments) |
| 6 | Sprint page: list and board | done | Foreman (FOR-26) | `pages/sprint/` |
| 7 | API: a task's changed files, diff and checks | done | Foreman (FOR-24) | endpoints |
| 8 | Task page: decision, Overview, Changes, Checks, Activity | done | Foreman (FOR-27, FOR-37), run commits by Claude (FOR-38) | `pages/task/`, migration 23 |
| 9 | Manager side bar; the manager proposes, a person confirms | done | Foreman (FOR-28, FOR-40) | `pages/manager/`, ADR-0022, migration 22 |
| 10 | Project settings: General and Workflow | done | Foreman (FOR-29), Advanced and Working copies by Claude | `pages/settings/` |
| 11 | Workspace settings and the user menu | done | Foreman (FOR-30) | `pages/workspaceSettings/` |
| 12 | The wordmark, icons, motion, live updates | done | Claude | `ui/Logo`, `ui/Icon`, `styles/motion.css`, `app/useLiveData.js` |
| 13 | Remove the old frontend and `/dashboard/legacy` | done | Foreman (FOR-35) | old files deleted, `legacy-capabilities.md` |
| 14 | Bundle out of git | done | Claude | ADR-0020 decision 10, `dashboard_runtime.py` builds it |
| 15 | Owner review of the running dashboard: one audit against written rules, fixed in one batch | done | Claude | `docs/prs/fix-design-audit.md`, rules in `docs/TESTING.md` |
| 16 | What the old dashboard could do and the new one could not: add a project, cancel, delete and reorder sprints, sign in, task details, new-task fields, advanced settings, working copies | done | Claude | four `feat/dashboard-*` branches |
| 17 | A way to see the look without a person: `scripts/dashboard_shot.mjs` | done | Claude | script, `docs/TESTING.md` |
| 18 | ESLint, a `lint` script and a CI step | todo | Claude | |
| 19 | Close the sprint: checkpoint, archive | todo | Claude | `docs/checkpoints/`, `docs/sprints/archive/` |

### Risks

- Tasks are larger than the ones Foreman has run here before (sprint 56 ran
  three small fixes). A task that does not converge is split, not retried
  indefinitely.
- The built bundle is committed, so two frontend branches open at once would
  conflict in it. Tasks run one at a time, each from the merged `main`.
- The backlog (slice 3) changes what the "Intake queue" sprint means. It is
  the one slice that reshapes a write path; its ADR is reviewed before its
  code.
- Agents cannot see the look. Review at the gate checks structure, tokens
  and tests; the owner checks the look in the running dashboard.

### Validation

Per slice, before merge: `./venv/bin/python -m unittest discover -s tests`,
`npm --prefix frontend test`, `npm --prefix frontend run build` with no
diff in `foreman/dashboard_frontend_dist`, `ruff check`, and
`./venv/bin/python scripts/validate_repo_memory.py`. Then the page is
opened in the running dashboard.

### Foreman on this sprint

Nineteen tasks (FOR-17 to FOR-30, FOR-33 to FOR-35, FOR-37, FOR-40) went
through the whole workflow and merged; notional spend about $106 on the
Foreman project's own accounting, which overcounts resumed sessions.

What worked: tasks of 500 to 1,500 changed lines converged with a precise
description and acceptance criteria; the test step caught real failures;
worktrees kept parallel tasks apart; the merge gate was the right place to
read a diff.

What did not:

- The first task blocked with "Missing completion marker": its 140-second
  test run was put in the background by the agent CLI and the turn ended.
  Fixed in the runner's environment (`HEADLESS_STEP_ENV`).
- The reviewer approved a 1,310-line change in seven seconds on a cut-off
  diff. Prompts and the diff cap were changed; the behaviour is not proven.
- While the built bundle was in git, any two frontend branches conflicted;
  one task was rebased four times. The bundle left git (slice 14).
- The engine does not push, merges only between steps, applies `run-task` at
  its next pass, and has no way to mark a task done by hand.
- Agents cannot see a page. Every look problem the owner found (a button in
  a tab row, a breadcrumb step that did not lead to itself, titles floating
  above what they name, uneven rows) passed tests and review. Slice 17 and
  the written rules are the answer: the look is now checked before a person
  sees it.
- Narrating the engine's progress while also asking the owner to review
  pages was too much at once, and the owner stopped it.

The defects are listed in `docs/sprints/backlog.md`.
