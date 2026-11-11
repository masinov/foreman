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
| 1 | `foreman/engine/` package, first cut: move the parts of `orchestrator.py` that are already separable (completion evidence, output contract and signal parsing, model selection, timeouts and cost ceilings) into modules with their own tests; `foreman.orchestrator` keeps re-exporting what callers import | todo | Claude, by hand | `foreman/engine/` |
| 2 | Engine package, second cut: task selection and leasing, recovery, the workflow step loop and its guards as separate modules; `ForemanOrchestrator` becomes a thin composition | todo | Claude, by hand | `foreman/engine/` |
| 3 | `foreman/store/` package: one transaction helper used by every write, a module per aggregate (projects, sprints, tasks, runs and events, leases and locks, engine commands, notifications, tokens), `ForemanStore` kept as the facade | todo | Claude, by hand | `foreman/store/` |
| 4 | One mutation service for task and sprint changes, used by the CLI and the dashboard: validates, writes, emits the audit event, and refuses what a running engine owns | todo | Claude, by hand | `foreman/mutations.py`, CLI and service call it |
| 5 | `foreman/cli/` package: a module per command group with `register()`, one top-level error boundary, `--json` on read commands | todo | to decide | `foreman/cli/` |
| 6 | Dashboard API: routers per resource, Pydantic request and response models, one error envelope, `/api/v1` (old paths kept as aliases for one release), pagination on list endpoints, a project-level event stream | todo | Claude, by hand | `foreman/dashboard/` |
| 7 | Roles, workflows and templates as package data; one version source | todo | Foreman | packaging |
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
