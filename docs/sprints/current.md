# Current Sprint

- Sprint: `sprint-53-phase0-unattended-safety`
- Opened: 2026-09-04
- Source: `docs/reviews/production-readiness-review.md`, Phase 0
- Goal: make an unattended `foreman run` safe on one machine before any
  shared or team deployment. Every slice below closes defects that would
  hang, corrupt, or silently misdirect an engine nobody is watching.

## Slices

| # | Slice | Branch | Status | Deliverable |
|---|-------|--------|--------|-------------|
| 1 | Store safety | `fix/store-concurrency-safety` | done | Migration 14 (gate tables rebuilt with `ON DELETE` rules, `events(task_id, timestamp)` index, per-project task-key sequence with a unique index); WAL + `synchronous=NORMAL` + 30 s busy timeout + retrying hot writes; atomic per-migration transactions; dependent-aware `delete_task` / `delete_sprint` / `prune_old_runs`; dashboard initializes the schema once; settings validated at `foreman config --set`, the dashboard settings endpoint, and the start of every run; `tests/test_store_safety.py` |
| 2 | Runner process lifecycle | `fix/runner-process-lifecycle` | todo | Reader thread with wall-clock time, cost, and heartbeat enforcement; process groups and group kill; stderr drained; UTF-8 with replacement; SIGTERM and atexit cleanup that kills the group and releases the lease; timeout on `_builtin:run_tests` |
| 3 | Output contract and signals | `fix/output-contract-and-signals` | todo | Marker and verdict extracted from the final assistant message only; multiple distinct verdicts become `error`; signals parsed once and deduplicated; per-role signal allowlist; reviewer outcomes declared in role TOML instead of hardcoded role ids |
| 4 | Workflow order and merge gate | `fix/workflow-test-before-review` | todo | `develop → test → review → merge` in all four shipped workflows; a project setting that inserts a human gate before merge in the default workflow |
| 5 | Dashboard minimum safety | `fix/dashboard-minimum-safety` | todo | Loopback bind by default, no wildcard CORS, shared-token auth dependency on every route, manager chat refused on non-loopback binds until Phase 1 hardens it |
| 6 | Cleanup | `chore/remove-bootstrap-supervisors` | todo | Remove `scripts/reviewed_claude.py`, `scripts/reviewed_codex.py`, and their tests; drop the unused `anthropic` dependency; gate autonomous-mode contract checks behind the mode flag |

## Sprint acceptance

- the full backend suite is green after every slice and each slice lands on
  `main` with a PR note under `docs/prs/`,
- `scripts/validate_repo_memory.py` is clean,
- the repo's own dogfood database upgrades in place with `foreman db migrate`,
- no slice introduces a surface that Phase 1 is known to replace.

## Previous sprint

Sprint 52 closed the review roadmap (`docs/specs/review.md`, Phases 0–7) at
`35b667c`. Sprints 49–52 are archived under `docs/sprints/archive/`; the
frontend UX and binding work that followed (`feat/frontend-backend-binding`
through `fix/frontend-landing-copy`) landed on `main` without a sprint, and
its record lives in `docs/reviews/frontend-ux-review.md` and `CHANGELOG.md`.
