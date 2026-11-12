# Current Sprint

## Sprint 58 — frontend rebuild

- **Opened:** 2026-11-12, from Phase 4 of
  `docs/reviews/2026-11-10-full-review-and-finish-plan.md`
- **Status:** in_progress
- **Method:** the owner asked for Foreman to build this itself. Every slice
  except the design reference is filed as a task in this repository's
  Foreman project (sprint `Sprint 58: frontend rebuild`) and run by the
  engine. Claude plans the tasks, reviews each diff at the merge gate, runs
  the suites, and approves or sends back under the owner's standing
  permission. What Foreman does well and badly on this work is recorded
  below as it happens.

### Goal

The dashboard is the one in `docs/design/dashboard-v7/` (ADR-0020): four
levels, one page each; the manager as a side bar; settings as their own
pages; a backlog; lists that page. The old frontend is gone.

### Constraints

- ADR-0020 is binding: source layout, routes, data hooks, class-based CSS
  from tokens, tests with each page, bundle rebuilt and committed.
- Nothing an operator can do today is lost between merges: the old
  application stays at `/dashboard/legacy` until the last slice removes it.
- API changes follow ADR-0019 (`/api/v1`, one error envelope) and keep the
  CLI and the dashboard on the same mutation service.
- Tasks do not edit `CHANGELOG.md` or this file (every branch touching the
  same lines conflicts at merge); the entry is added when the task lands.
- No real browser on the development host. Page tests run in jsdom; the look
  is checked by a person.

### Affected areas

`frontend/src/` (rewritten), `foreman/dashboard_frontend_dist` (rebuilt),
`foreman/dashboard/` routers and `foreman/dashboard_service.py` (new
endpoints), `foreman/mutations.py` and the store (backlog), tests on both
sides, `docs/`.

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 0 | Design reference in the repository, ADR-0020, pointers in `AGENTS.md` and the other docs, sprint 57 archived | done | Claude, by hand | `docs/dashboard-design-v7`: `docs/design/dashboard-v7/`, ADR-0020 |
| 1 | Frontend foundation: tokens, primitives, shell, router, API client and hooks, the workspace page; old application moved to `/dashboard/legacy` | todo | Foreman | new `frontend/src/` layout, workspace page, tests |
| 2 | API: workspace overview, needs-you across projects, project milestones, sprint list paging and filtering | todo | Foreman | endpoints under `/api/v1`, tests |
| 3 | Backlog: unplanned work has a place that is not a sprint; accept, decline, plan into a sprint; agent-created tasks land there | todo | Foreman | ADR, store and mutation changes, endpoints, CLI, tests |
| 4 | Project page: engine, needs you, the sprint queue with finished sprints behind a disclosure, Activity tab | todo | Foreman | `pages/project/`, tests |
| 5 | Backlog tab | todo | Foreman | `pages/project/` backlog, tests |
| 6 | Sprint page: list and board | todo | Foreman | `pages/sprint/`, tests |
| 7 | API: a task's changed files, diff and checks as facts and claims | todo | Foreman | endpoints, tests |
| 8 | Task page: decision, Overview, Changes, Checks, Activity | todo | Foreman | `pages/task/`, tests |
| 9 | Manager side bar on project, sprint and task pages | todo | Foreman | shell slot filled, tests |
| 10 | Project settings: General and Workflow | todo | Foreman | `pages/settings/`, endpoints as needed, tests |
| 11 | Workspace settings and the user menu | todo | Foreman | `pages/settings/`, endpoints as needed, tests |
| 12 | The mark, motion, and live updates from the event streams | todo | Foreman | `ui/mark`, stream refresh in hooks, tests |
| 13 | Remove the old frontend and `/dashboard/legacy`; docs | todo | Foreman | old files deleted, `docs/ARCHITECTURE.md`, `docs/TESTING.md` |

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

Recorded as tasks land: model, runs, tokens (input / output / cache),
notional cost, what the review caught, what Claude had to correct.
