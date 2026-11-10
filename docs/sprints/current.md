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
| 0 | Baseline: merge the three operator UI fixes with `main`, rebuild the bundle, CI, ruff baseline, compact STATUS, review in the repo | done (unmerged) | Claude, by hand | `chore/phase0-baseline`, `.github/workflows/ci.yml`, `docs/prs/chore-phase0-baseline.md` |
| 1 | Browser-origin defence: JSON content type required on mutating routes, Origin and Host checks, a token always required (generated for loopback), no token in query strings except the stream, `/docs` behind the token | todo | | backend, runtime, frontend token bootstrap, tests |
| 2 | Host-level settings out of the general API: `test_command`, `worktree_setup_command`, `worktree_root`, `context_dir`, `judge_*`, role backend and permission mode are operator-only (CLI); prune only git-registered worktrees of the project; http(s)-only source URLs | todo | | service, worktrees, CLI, tests |
| 3 | Real cost control: `--max-budget-usd`, usage from `message.usage` including cache tokens, a gate never drops `agent.completed`, per-role ceilings, `0` means off | todo | | runner, roles, orchestrator, tests |
| 4 | Runner termination contract: stop at the terminal event, always kill the process group, SIGHUP handler, parent-death signal | todo | | `runner/process.py`, runners, tests |
| 5 | Task lease lifecycle: timer heartbeat for the whole hold, no self-expiry in stale-run recovery, one `block_task()` helper that releases the lease | todo | | orchestrator, store, tests |
| 6 | Approve and deny record a decision and enqueue an engine command; no workflow execution in the CLI or the web process | todo | | orchestrator, serve, CLI, service, ADR-0011 amendment, tests |
| 7 | First delegation trial: one self-contained slice from Phase 2 run through Foreman on a cheaper model, compared with a by-hand slice of similar size | todo | | cost and outcome note in this file |

### Carried from sprint 54

- Planner step per task (old slice 5) moves to Phase 5 of the finish plan.
- Database reconciliation for FOR-11 and FOR-12 waits for owner confirmation
  (see `docs/STATUS.md`).
