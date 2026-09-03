# Sprint 53 — Phase 0 Unattended Safety

- **Opened:** 2026-09-04, from Phase 0 of
  `docs/reviews/production-readiness-review.md`
- **Closed:** 2026-09-04
- **Status:** done

## Goal

Make an unattended `foreman run` safe on one machine before any shared or
team deployment: no hang on a silent agent, no leaked agent process group, no
foreign-key crash on retention, one SQLite file shared safely by the engine,
the dashboard, and the CLI, a contract read from the agent's final message,
tests before review with a policy-governed merge gate, and a dashboard that
cannot be reached unauthenticated off-loopback.

## Slices

| # | Slice | Branch | Merged at | Deliverable |
|---|-------|--------|-----------|-------------|
| 1 | Store safety | `fix/store-concurrency-safety` | `9d23fe0` | Migration 14 (cascading gate tables, `events(task_id, timestamp)` index, task-key sequence with a unique index); WAL, busy timeout, retrying hot writes; atomic per-migration transactions; dependent-aware deletes; dashboard initializes once; settings validated at run start, the dashboard endpoint, and `foreman config --set`; retention opt-in. `tests/test_store_safety.py` (+20) |
| 2 | Runner process lifecycle | `fix/runner-process-lifecycle` | `79d499a` | `foreman/runner/process.py`: pumped streams, silent-tick wake-ups, own session, process-group terminate and kill, shutdown handlers raising `EngineShutdown`; both runners rebuilt on it; `agent.tick` heartbeats; `LeaseLostError`; runs settled as `killed` on interruption with the task resumable; `test_timeout_seconds`; `foreman run` exits 130 when stopped. `tests/test_runner_lifecycle.py` (+15) |
| 3 | Output contract and signals | `fix/output-contract-and-signals` | `2d9829a` | Final-message contract; decision grammar with ambiguity and undeclared-verdict errors; role-declared `outcomes`, `review_kind`, and `signals` replacing hardcoded reviewer ids in normalization, workflow validation, and evidence (tiered approvals now pass the guard); fence-aware, multi-line, deduplicated signals with `signal.rejected`; built-ins take the orchestrator's evidence builder. `tests/test_output_contract.py` (+18) |
| 4 | Workflow order and merge gate | `fix/workflow-test-before-review` | `10333ef` | All four workflows `develop → test → reviews → merge_approval → merge → done`; gate steps carry a `policy`; `merge_approval` / `plan_approval` settings and per-task `executor_overrides.gates`; auto gates record a `policy:<name>` decision; reviewer summary from the latest agent run; `foreman task override --gate`. `tests/test_workflow_gates.py` (+11) |
| 5 | Dashboard minimum safety | `fix/dashboard-minimum-safety` | `8074eda` | Shared-token auth on `/api` (header or stream query), no wildcard CORS, non-loopback binds refused without a token, manager chat loopback-only unless allowed, repo-path validation, bounded events page, frontend token prompt. `tests/test_dashboard_safety.py` (+12), `frontend/src/api.test.js` (+5) |
| 6 | Cleanup | `chore/remove-bootstrap-supervisors` | fast-forwarded to `main` at sprint close | Bootstrap supervisor scripts, their tests, the supervisor-state adapter, and the legacy `finalize_supervisor_merge` removed; unused `anthropic` dependency dropped; autonomous contract text only for autonomous projects; sprint archived |

## Test results

- Backend suite at close: **605 tests passing** (585 at sprint
  open; 76 added across slices 1–5, 56 removed with the bootstrap code).
- Frontend: 18 passing.
- `scripts/validate_repo_memory.py` clean after every slice.

## Notes / risks

- `merge_approval` defaults to `auto` to keep existing projects unattended;
  production projects must set it to `human` until Phase 1 moves the
  authorization onto the pull request.
- The spec's workflow order (review before test) is now a documented
  conflict in `docs/STATUS.md`; the spec text was not revised.
- The shared dashboard token is not identity; Phase 1 adds login and actor
  columns.
- Per-task leases remain; Phase 1 replaces them with a project engine lock
  until parallel workers return the need for per-task ownership.

## Follow-ups (moved to backlog)

- Phase 1: resident `foreman serve` worker, intake endpoint, policy matrix,
  planner step, worktree per task, pull-request integration, facts-based
  verification, identity and notifications, manager chat hardening,
  session key on model and endpoint, migrations as a deploy step, database
  out of the repository, frontend split and CI-built bundle.
