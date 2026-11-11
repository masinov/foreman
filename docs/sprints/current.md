# Current Sprint

## Sprint 57 — structure

- **Opened:** 2026-11-11, from Phase 3 of
  `docs/reviews/2026-11-10-full-review-and-finish-plan.md`
- **Status:** in_progress
- **Method:** Claude drives. Every slice is behaviour-preserving: code moves,
  the tests that cover it keep passing unchanged, and anything that has to
  change behaviour is split out and named. The whole suite runs before every
  merge. Mechanical, self-contained moves with an existing test net are
  candidates for Foreman; anything that reshapes a write path is done by
  hand.

### Goal

The code is organised the way the product is: an engine package, a store
package, one mutation service, a CLI package, a routed and versioned API,
and tests split along the same lines. No file is the place where everything
lives.

### Starting point

| File | Lines |
|---|---|
| `foreman/orchestrator.py` | 4574 |
| `foreman/cli.py` | 4009 |
| `foreman/store.py` | 3213 |
| `foreman/dashboard_service.py` | 2122 |
| `tests/test_orchestrator.py` | about 8000 |

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 1 | `foreman/engine/` package, first cut: errors, results, limits, model selection, output contract and the evidence builder moved out of `orchestrator.py` (4574 to 3754 lines); tests import from the new modules | done | Claude, by hand | `refactor/engine-package`: `foreman/engine/` (7 modules) |
| 2a | Engine package, second cut: task leasing (`TaskLeases`), run and event recording (`RunRecords`), branch sync, prompt-context and gate helpers out of `orchestrator.py` (now 3144 lines) | done | Claude, by hand | `refactor/engine-leases-and-records` |
| 2b | Engine package, third cut: task writes, retention, sprint flow, recovery, selection, signals, agent-step execution, prompt building and task worktrees as collaborators; the 750-line step loop split into named phases | done | Claude, by hand | `refactor/engine-collaborators`: 10 more `foreman/engine/` modules; `orchestrator.py` 1883 lines |
| 2c | What is left in `orchestrator.py`: the step phases, `resume_human_gate` (188 lines) and `_run_leased_task` (110) still live on `ForemanOrchestrator`; the agent step's corrective retry duplicates its first attempt | todo | Claude, by hand | a workflow-runner class, one attempt function |
| 3 | `foreman/store/` package: `base`, `rows` and a module per aggregate; `ForemanStore` kept as the facade; every write retries on a held database lock (20 did not) | done | Claude, by hand | `refactor/store-package`: 14 modules, 1 test |
| 4 | One mutation service for task and sprint changes, used by the CLI and the dashboard: validates, refuses what a running engine is executing, writes, and records an audit event with the actor and the surface | done | Claude, by hand | `refactor/mutation-service`: `foreman/mutations.py`, CLI handlers, dashboard service, `tests/test_mutations.py` (11 tests). Not covered: task and sprint create and field edits still live in each surface; sprint changes record no event (events need a task) |
| 5 | `foreman/cli/` package: a module per command group with `register_<command>()`, one top-level error boundary, `--json` on four read commands | done | Claude, by hand | `refactor/cli-package`: 14 modules, `tests/test_cli_package.py` (11 tests). `--json` is not yet on `status`, `board`, `cost`, `history`, `task show`, `project`, `worktree list`, `token list`, `notify list`, `roles`, `workflows`, `db version` |
| 6a | Dashboard API: routers per resource, `/api/v1` with `/api` kept as an alias, one error envelope with a code | done | Claude, by hand | `refactor/dashboard-api`: `foreman/dashboard/`, ADR-0019, `tests/test_dashboard_api.py` (8 tests) |
| 6b | Dashboard API: handlers off the event loop, typed request bodies for the fixed-shape write routes, a project-level event stream | done | Claude, by hand | `refactor/api-handlers-off-loop`: `schemas.py`, `streaming.py`, 11 tests. Left for the frontend rebuild to ask for: response models and pagination on the sprint and task lists (events already page) |
| 7 | Roles, workflows and templates as package data; one version source | done | Claude, by hand (three directory moves and a packaging check; smaller than the brief a delegated task would need) | `chore/package-data`: `foreman/data/`, `pyproject.toml`, `tests/test_packaging.py` (3 tests); a built wheel was unpacked and run |
| 8 | Tests split along the new modules with shared fixtures; `test_git.py`; store concurrency tests | todo | Foreman for the additions, by hand for the split | `tests/` |
| 9 | Built frontend bundle out of git: built in CI and at install, with the freshness check replaced by a build step | todo | to decide | CI, packaging |

### Carried from sprint 56

- A planted-defect test of the reviewer roles.
- The fencing token on leases is unchecked on writes (returns with parallel
  workers).
- `foreman task block` on a running task does not interrupt the agent
  mid-step; `stop-task` does.
- A stale `running` agent run is reset to the entry step; resuming it in
  place is not built.
- Python `Enum` classes for statuses; the judge takes a mapping, not the
  settings object.
- No end-to-end CLI test of interrupting a one-shot `foreman run` with an
  engine command.
