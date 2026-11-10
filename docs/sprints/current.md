# Current Sprint

## Sprint 55 — baseline and host safety

- **Opened:** 2026-11-10, from Phases 0 and 1 of
  `docs/reviews/2026-11-10-full-review-and-finish-plan.md`
- **Status:** in_progress
- **Method:** Claude drives. Each slice records who executed it (by hand or
  through Foreman, and with which model) and what it cost, so the sprint also
  measures where delegation is safe and cheaper. Slices 1 to 6 are done by
  hand: they fix the engine and the host exposure, so the engine should not
  be the thing running them.

### Goal

A clean, CI-checked baseline, then an engine and dashboard that are safe to
run on a developer machine: no code execution through the API, no runaway
spend, no orphaned agents, and one engine per project in fact.

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 0 | Baseline: merge the three operator UI fixes with `main`, rebuild the bundle, CI, ruff baseline, compact STATUS, review in the repo | done | Claude, by hand | `chore/phase0-baseline`, `.github/workflows/ci.yml`, `docs/prs/chore-phase0-baseline.md` |
| 1 | Browser-origin defence: Host check on token-less binds, Origin and `Sec-Fetch-Site` checks, JSON content type required for bodies, query-string token on GET only, generated docs routes off | done | Claude, by hand | `fix/dashboard-browser-origin-defence`: `foreman/dashboard_guard.py`, ADR-0016, 12 tests in `tests/test_dashboard_safety.py`, live check with attack requests and a real browser |
| 2 | Host-level settings out of the general API: shell commands, storage paths, judge endpoint, and role backend and permission mode are refused over HTTP and shown read-only; prune deletes only git worktrees of the project; http(s)-only source URLs; atomic role writes | done | Claude, by hand | `fix/host-level-settings`: `HOST_LEVEL_SETTINGS`, service and worktree changes, ADR-0017, 11 Python tests and 1 frontend test |
| 3 | Real cost control: the per-run ceiling is passed to Claude Code as `--max-budget-usd`; a finished run is never turned into a kill; a budget stop is a cost kill that keeps its cost; role ceilings of $2 to $30 in place of $1,000; `runner_max_cost_usd` can lower a role ceiling; a cost limit of 0 means off; reading stops at the result line and leftover process groups are swept | done | Claude, by hand | `fix/runner-cost-control`: runner, process, orchestrator, `roles/*.toml`, 8 tests |
| 4 | Runner termination contract: stop at the terminal event, always kill the process group, SIGHUP handler, parent-death signal | todo | | `runner/process.py`, runners, tests |
| 5 | Task lease lifecycle: timer heartbeat for the whole hold, no self-expiry in stale-run recovery, one `block_task()` helper that releases the lease | todo | | orchestrator, store, tests |
| 6 | Approve and deny record a decision and enqueue an engine command; no workflow execution in the CLI or the web process | todo | | orchestrator, serve, CLI, service, ADR-0011 amendment, tests |
| 7 | First delegation trial: one self-contained slice from Phase 2 run through Foreman on a cheaper model, compared with a by-hand slice of similar size | todo | | cost and outcome note in this file |

### Carried from sprint 54

- Planner step per task (old slice 5) moves to Phase 5 of the finish plan.
- Done 2026-11-10 with owner confirmation: FOR-12 marked done and its
  worktree removed, FOR-11 cancelled, sprint 54 completed in the database,
  47 merged local branches deleted, slices 0 and 1 merged and pushed.

### CI

The first run on GitHub failed in the Python job: `tests/test_cli.py`
reinstalls the package with `--no-build-isolation`, and a fresh 3.12
virtualenv has no setuptools. Reproduced in a clean clone and fixed in the
workflow. The frontend job, including the bundle-freshness check, passed.

### Still open in the live database

Seven task leases from sprint 54 are still marked `active` (long expired,
on finished tasks). They are harmless and are evidence for slice 5, which
makes every exit path release its lease.

### Slice 1 notes

The planned "token always required, generated for loopback" was dropped: the
Host and Origin checks close both browser routes without adding a secret to
bootstrap and store. Rationale in ADR-0016.

### Slice 3 notes

- Cost only arrives in Claude Code's final result line, so Foreman cannot
  meter a run in flight. The ceiling is therefore enforced by the CLI
  (`--max-budget-usd`). Not verified against a real over-budget run (it
  would cost money): the result subtype is matched on `max_budget`; if the
  CLI words it differently the run is recorded as a failed run with its cost
  instead of a cost kill, and spend still stops.
- Part of slice 4 landed here because it is the same loop: the runner stops
  reading at the result line, waits at most five seconds for the process to
  exit, and kills what is left of its process group even after a normal
  exit. Slice 4 keeps SIGHUP and the parent-death signal.
- Left open: token counts still ignore cache tokens (changing that changes
  every number the dashboard shows and needs a decision on what "tokens"
  means), and Codex still reports no cost.
