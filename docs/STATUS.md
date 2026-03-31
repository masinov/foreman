# STATUS

## Current sprint

- Sprint: `sprint-27-e2e-dashboard-validation`
- Status: done
- Goal: add browser-driven end-to-end validation of the Foreman dashboard
  through a real Chromium browser against a live FastAPI server and seeded
  SQLite database

## Active branches

- no long-lived feature branch should remain loose after the engine DB
  discovery, security-review, backend-preflight, and retention slices; start
  product-surface hardening work from `main`

## Completed this week

- reconciled the previously loose feature and recovery histories into one
  integrated mainline and pushed the result to `origin/main`
- completed `sprint-14-dashboard-streaming-transport`
- added a dedicated dashboard sprint event stream with incremental persisted
  event delivery
- switched the dashboard activity panel to a live subscription path and
  debounced task-state refresh on incoming events
- completed `sprint-15-engine-db-discovery`
- added repo-local SQLite discovery using a hidden `.foreman.db` file
- made `foreman init` default to `<repo>/.foreman.db` while keeping `--db` as
  a deterministic override
- wired `projects`, `status`, monitoring commands, approve or deny, and the
  dashboard CLI entrypoint to use repo-local DB discovery without explicit
  flags
- updated scaffold generation so the default `.foreman.db` stays gitignored
- completed `sprint-16-security-review-workflow`
- added end-to-end orchestrator coverage for the shipped
  `development_secure` workflow variant
- covered security-review approval and denial transitions explicitly,
  including carry-output back into development after a denial
- documented how bootstrap project initialization should opt into
  `development_secure`
- completed `sprint-17-native-backend-preflight-checks`
- added explicit native backend preflight failure handling for missing Claude
  or Codex executables and malformed Codex startup responses
- made backend preflight failures fail once before `agent.started` instead of
  consuming infrastructure retries
- documented backend prerequisites and recovery expectations for operators
- completed `sprint-18-event-retention-pruning`
- added store-backed pruning of old project events by cutoff while preserving
  blocked and in-progress task history
- wired orchestrator startup to honor `event_retention_days` and emit
  `engine.event_pruned` when rows are removed
- documented retention boundaries, including the current schema constraint
  that pruning records still attach to a task-bound synthetic run
- completed `sprint-19-watch-live-tail-alignment`
- replaced bounded `foreman watch` snapshots with a persisted live tail for
  project, sprint, and run scopes
- aligned CLI watch delivery with the dashboard's cursor-based sprint-event
  model while keeping the CLI on a direct store-read transport
- documented the new watch boundary and advanced repo memory to the migration
  framework slice
- completed `sprint-20-production-hardening-reset`
- tightened repo instructions so bootstrap state now refers only to project
  memory and feature coverage, not to acceptable implementation quality
- accepted a dedicated web UI and API boundary that deprecates embedding the
  product dashboard inside one Python module
- recorded a ranked hardening detour for dashboard replacement, stub removal,
  migration work, and broader product-surface remediation
- completed `sprint-21-dashboard-api-extraction`
- extracted dashboard reads, task actions, and streaming payload assembly into
  what is now `foreman/dashboard_service.py`
- reduced the old `foreman/dashboard.py` module into a thinner HTTP adapter
  over the extracted backend contract while preserving the legacy dashboard
  shell during the transition
- strengthened dashboard regression coverage around API and SSE payload
  contracts to prepare the React handoff
- completed `sprint-22-dashboard-backend-foundation`
- replaced the raw dashboard stdlib server with a FastAPI backend in
  `foreman/dashboard_backend.py`
- switched `foreman dashboard` to a uvicorn-backed runtime while preserving
  the transitional dashboard shell and current JSON plus SSE routes
- added ASGI-backed dashboard HTTP tests so the backend is validated as a real
  app, not only as a service layer
- completed `sprint-23-react-dashboard-foundation`
- added a dedicated React and Vite frontend workspace in `frontend/` for the
  shipped dashboard surfaces
- removed the embedded dashboard HTML, CSS, and browser logic from Python and
  switched FastAPI to serve built frontend assets from
  `foreman/dashboard_frontend_dist/`
- added frontend component tests and bundle-build validation alongside the
  existing dashboard API and FastAPI regression suite
- pruned redundant dashboard transition checkpoint and PR-summary docs that no
  longer add repo-memory value after the React cutover
- clarified the live dashboard module split by renaming the runtime wrapper to
  `foreman/dashboard_runtime.py` and the service layer to
  `foreman/dashboard_service.py`
- added frontend-dev support to `foreman dashboard`, Vite `/api` proxying, and
  a one-command `npm --prefix frontend run dev:full` launcher for local
  dashboard work
- implemented the remaining shipped CLI product commands instead of routing
  them through `handle_stub`
- added real project, sprint, task, run, and config command behavior for the
  shipped CLI surface, including repo-local DB discovery support and stateful
  task or sprint transitions
- expanded CLI subprocess coverage to validate the hardened command surface
  end to end
- closed the most visible product-surface gaps after the dashboard frontend
  cutover
- added a settings panel, sprint creation, and task creation backed by real
  FastAPI endpoints and the dashboard service layer
- added `SettingsPanel`, `NewSprintModal`, and `NewTaskModal` React components
  wired into the dashboard app with validation and error handling
- strengthened product-surface validation with 15 new integration tests
  covering settings read/update, sprint creation, and task creation through
  both the service layer and FastAPI transport
- completed `sprint-25-migration-framework-bootstrap`
- replaced bootstrap DDL with a version-tracked migration framework in
  `foreman/migrations.py` and `foreman/store.py`
- `ForemanStore.initialize()` now creates a `schema_migrations` table and
  applies any unapplied migrations in version order; idempotent on repeat calls
- `ForemanStore.schema_version()` returns the highest applied migration version
- migration 1 is the current baseline schema; appending to `MIGRATIONS` is the
  only step required to add a schema change in future sprints
- 17 new tests in `tests/test_migrations.py` cover list integrity, fresh
  install, idempotency, incremental upgrade, and version tracking
- accepted `docs/adr/ADR-0005-schema-migration-strategy.md`
- completed `sprint-26-history-lifecycle-expansion`
- added migration 2 (`idx_runs_project_completed`) — `test_partial_db_upgraded_to_latest`
  now passes (was previously skipped)
- added `ForemanStore.prune_old_runs()`: hard-deletes terminal runs and their
  cascaded events older than a cutoff; protects blocked/in-progress task runs
- added `ForemanStore.strip_old_run_prompts()`: nulls `prompt_text` on old
  terminal runs without deleting the run record or its telemetry
- expanded orchestrator startup pruning via `prune_old_history()` which reads
  `run_retention_days` and `prompt_retention_days` from project settings
  alongside the existing `event_retention_days`; emits `engine.run_pruned` and
  `engine.prompt_stripped` lifecycle events
- 19 new tests in `tests/test_run_retention.py`; 188 tests pass total
- completed `sprint-27-e2e-dashboard-validation`
- installed `playwright` and `pytest-playwright`; Chromium browser binaries available
- added `tests/test_e2e.py` with 20 Playwright E2E tests driven against a real
  uvicorn dashboard server and seeded SQLite database; covers dashboard load,
  project/sprint navigation, task detail drawer, settings panel, sprint
  creation, and task creation end to end
- E2E tests skip gracefully when Playwright is not installed
- 208 tests pass total (20 new E2E + 188 prior)

## Current repo state

- The repository now contains:
  - the product spec and UI mockup,
  - the `foreman` package with SQLite-backed models, store, loaders, CLI, and
    orchestrator,
  - runtime `.foreman/context.md` and `.foreman/status.md` projection from
    SQLite,
  - repo-local `.foreman.db` discovery for normal CLI usage with `--db` still
    available as an explicit override,
  - persisted human-gate approval and denial commands with deferred or
    immediate native resume behavior,
  - the opt-in `development_secure` workflow executing code review, security
    review, test, and merge with durable transition state,
  - native Claude Code and Codex runners with structured event capture,
    explicit startup preflight checks, approval-policy handling, retry
    normalization, and persisted session reuse across fresh orchestrator
    invocations for persistent roles,
  - orchestrator startup event-retention pruning driven by
    `event_retention_days`, with durable `engine.event_pruned` records and
    protection for blocked and in-progress task history,
  - monitoring CLI surfaces for board, history, cost, and live watch tails
    across project, sprint, and run scopes,
  - accepted ADRs for runner session semantics, dashboard data access, the
    dedicated product web UI boundary, and the FastAPI dashboard backend
    framework,
  - a dashboard service layer in `foreman/dashboard_service.py` covering
    project, sprint, task, action, and incremental streaming payloads,
  - a FastAPI transport layer in `foreman/dashboard_backend.py` that serves
    the current dashboard routes, built frontend shell, and SSE stream through
    an actual ASGI app,
  - a dedicated React dashboard frontend in `frontend/` plus built assets in
    `foreman/dashboard_frontend_dist/`,
  - `foreman/dashboard_runtime.py` as the asset-aware uvicorn entrypoint for
    `foreman dashboard`, with an explicit frontend-dev mode that no longer
    requires built assets,
  - `frontend/vite.config.js` proxying `/api` to the local FastAPI backend and
    `scripts/dashboard_dev.py` providing a one-command frontend plus backend
    dev loop,
  - unit and integration coverage across store, CLI, orchestrator, runners,
    dashboard, the React frontend, scaffold, and executor seams,
  - a version-tracked schema migration framework (`foreman/migrations.py`,
    `schema_migrations` table, `ForemanStore.migrate()`,
    `ForemanStore.schema_version()`),
  - run and prompt retention via `ForemanStore.prune_old_runs()` and
    `ForemanStore.strip_old_run_prompts()`, wired into orchestrator startup
    via `prune_old_history()`,
  - 20 browser-driven E2E tests in `tests/test_e2e.py` covering the full
    FastAPI + SQLite + React dashboard stack via Playwright and Chromium,
  - repo-memory docs that are intended to let a fresh agent continue from the
    next slice without reconstructing prior branch history.
- The temporary markdown sprint and status workflow remains intentional
  bootstrap state. The eventual product should move operational state into
  SQLite as described in the spec.

## Ready next

1. implement `task_selection_mode="autonomous"` in the orchestrator
2. add `foreman db migrate` CLI surface for operators to inspect schema version
   and apply pending migrations explicitly

## Open risks

- `reviewed_codex.py` and `reviewed_claude.py` are bootstrap supervisors, not
  the Foreman product itself; their behavior should not accidentally become the
  long-term architecture.
- Repo-local discovery currently depends on an existing `.foreman.db` in the
  current repo lineage or on `foreman init` creating one; cross-repo and
  out-of-repo inspection still requires explicit `--db`.
- the committed dashboard build output in `foreman/dashboard_frontend_dist/`
  must stay in sync with the source app in `frontend/`; E2E tests will fail
  if the build is stale.
- the sprint SSE path still polls SQLite directly inside the FastAPI stream
  loop; that is acceptable for now, but it is not a final transport design.
- Native backend preflight now validates executable presence and Codex startup
  handshake assumptions, but it does not yet prove downstream auth or service
  reachability beyond startup.
- The Codex app-server protocol exposes token usage but not USD pricing, so
  Codex runs currently persist `token_count` accurately while `cost_usd`
  remains `0.0`.
- `task_selection_mode=\"autonomous\"` is still not implemented in the
  orchestrator even though the project settings model exposes it.
- Run and prompt retention are controlled by optional project settings; if neither `run_retention_days` nor `prompt_retention_days` is set, old runs and prompts accumulate indefinitely.
- The migration framework covers DDL changes but does not yet provide a down/rollback path; adding that is deferred until a rollback scenario is observed in practice.
- project-scoped `foreman watch` resolves the active sprint once at startup;
  if sprint ownership changes mid-tail, operators currently need to restart
  the command to follow the new sprint.
- dashboard validation now covers the extracted service layer, FastAPI
  delivery, React component behavior, and browser-driven E2E flows via
  Playwright and Chromium.

## Documented conflicts

- The shipped workflow TOML treats `_builtin:mark_done` as a terminal step with
  no outbound transition, while the orchestrator pseudocode in the spec blocks
  any missing transition. The current implementation treats a step that sets
  task status to `done` as successful workflow termination and records that
  nuance here until the spec text is clarified.
- The spec's CLI examples omit explicit database selection and do not define a
  bootstrap discovery path. The current runtime defaults to repo-local
  `.foreman.db` discovery for normal flows and keeps `--db PATH` as an
  explicit override until engine-instance configuration exists.
- The spec expects `.foreman/status.md` to list open decisions, but the current
  SQLite schema has no structured decision records yet. The runtime projection
  currently emits an explicit placeholder until those records exist.
- The mockup is a static HTML interaction reference, not a frontend stack
  specification. The previous implementation treated that as enough license to
  embed the dashboard directly into a Python module; the active architecture
  direction now rejects that interpretation, and the shipped dashboard now
  follows the React plus FastAPI split.
- The spec describes `foreman approve` and `foreman deny` as immediately
  resuming workflow execution. The current runtime does that when the next
  backend and repo are available, but it still persists a deferred next step
  when the resumed workflow cannot execute safely yet.
- The spec's retry pseudocode retries every `InfrastructureError`. The current
  runtime now treats backend preflight failures as explicit non-retryable
  startup errors so missing executables or malformed startup handshakes fail
  once before `agent.started`.
- The spec describes `engine.event_pruned` as a project-level emit, but the
  current schema still requires non-null `run_id` and `task_id` on events. The
  runtime therefore records pruning through a synthetic orchestrator run
  attached to one stable project task.

## Open decisions

- whether the repo-local `.foreman.db` location should remain long-term or
  give way to a broader engine-instance configuration model
- whether project `default_model` should be validated against the selected
  backend instead of being passed through verbatim at runtime
- whether backend preflight should eventually expand beyond executable and
  startup-contract checks into authentication or service reachability checks
- whether run and prompt retention thresholds should have product-level defaults rather than requiring explicit project settings
- whether the secure workflow should remain an explicit opt-in at init time or
  be selected automatically from project policy in a later slice
- whether project-scoped watch should eventually auto-rebind if a different
  sprint becomes active during a long-lived tail session
