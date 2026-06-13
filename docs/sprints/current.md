# Current Sprint

- Active implementation sprint: **none.** The review roadmap
  (`docs/specs/review.md`, Phases 0–7) is fully implemented and merged to
  `main`.
- Last merged work: Sprints 49–52 (review Phases 2–7), fast-forwarded to `main`
  at `35b667c` on 2026-06-13 and archived under `docs/sprints/archive/`.
- Next: pull the next justified slice from `docs/sprints/backlog.md` (Tier 3
  architecture / parking-lot items) when a new sprint opens.

## Review Roadmap — Closed

`docs/specs/review.md` was executed as the forward implementation roadmap. All
phases are now on `main`:

| Phase | Sprint | Branch | Landed at | Archive |
|-------|--------|--------|-----------|---------|
| 0 | 47-adjacent | `fix/review-phase0-correctness` | `5883075` | inline below |
| 1 | 48 | `feat/worker-fleet-minimax-smoke` | `07649e6` | inline below |
| 2 | 49 | `feat/meta-agent-persistence` | `62c2e25` | `archive/sprint-49-meta-agent-persistence.md` |
| 3 | 50 | `feat/executor-overrides-ladder` | `2ca7b49` | `archive/sprint-50-executor-overrides-ladder.md` |
| 4–5 | 51 | `feat/judge-and-tiered-review` | `b53f930` | `archive/sprint-51-judge-and-tiered-review.md` |
| 6–7 | 52 | `feat/supervision-and-transport` | `35b667c` | `archive/sprint-52-supervision-and-transport.md` |

Full suite at close of Sprint 52: **571 tests passed**;
`scripts/validate_repo_memory.py` clean; `git diff --check` clean.

Open deferred follow-up (in backlog, not yet scheduled): a tool-enabled agentic
re-review when the frontier reviewer answers `STEER: need repository context`
(today routes back to develop).

## Earlier Sprint History (pre-roadmap, retained for context)

### Sprint 48 Outcome

- Sprint: `sprint-48-worker-fleet-minimax-smoke`
- Branch: `feat/worker-fleet-minimax-smoke`
- Merged to `main`: `07649e6`
- Deliverable: repeatable Claude Code/MiniMax M3 smoke plus the minimal
  role/env runner configuration needed to make Phase 1 model-endpoint work
  reliable (per-role `[agent.env]`, `foreman.runner.env.resolve_env()`, runner
  env plumbing, `roles/developer_worker.toml`).

### Sprint 47 Active-Run Lease Recovery

Implemented on `feat/active-run-lease-heartbeat-recovery` and merged to `main`
at `5fbfc26`: in-step native runner lease heartbeats, stale active-lease
liveness checks, forced resource-lease expiry for recovered stale runs, and
regression coverage.

### Review Integration

`docs/specs/review.md` was read as a backend implementation review and
completion roadmap. It does not supersede `docs/specs/engine-design-v3.md` for
product behavior or `docs/mockups/foreman-mockup-v6.html` for UI hierarchy.

Phase 0 correctness fixes were implemented on `fix/review-phase0-correctness`
and fast-forward merged to `main` at `5883075`:

1. `signal.task_created` persistence attaches `engine.task_created` to the
   active run.
2. `uuid4` imported for `foreman waive-merge` (covered end to end).
3. Dashboard human/stop events made FK-safe via a shared synthetic-run helper.
4. Dashboard run process tracking moved out of per-request service instances;
   spawned runs terminated on Stop; `agent_running` exposed in payloads.
5. Completion-evidence construction restricted to decision roles and
   invalidated when the task branch head changes.
6. Dashboard task cancellation aligned with CLI cancellation (clears workflow
   resume fields, sets `completed_at`).
7. Dead `foreman/executor.py` path removed.
