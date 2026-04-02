# STATUS

## Current sprint

- Sprint: `sprint-36-intervention-and-ordering` (completed 2026-04-02)
- Branch: `feat/sprint-36-intervention-and-ordering`

## Active branches

- `feat/sprint-36-intervention-and-ordering` — sprint list ordering,
  manual intervention controls, board layout fixes

## Completed this session (sprints 30–35)

- completed `sprint-30-wire-dead-surfaces`
- wired Stop agent button; `PATCH /api/sprints/{id}` lifecycle transitions
  (planned→active→completed/cancelled); `started_at`/`completed_at` set on
  transition; `PATCH /api/tasks/{id}` for description and priority; sprint
  status badges and Start/Complete buttons in sprint view header
- completed `sprint-31-backlog-items`
- sprint creation with inline tasks; task cancellation; task dependency display;
  event log load-more with cursor; cancelled sprint filter in list and kanban
- completed `sprint-32-tier1-editing`
- task field editing in `TaskDetailDrawer` (title, type, criteria); sprint goal
  inline editing; activity panel auto-scroll via `useLayoutEffect`
- completed `sprint-33-tier2-gaps`
- workflow step badge on task cards and drawer; project creation from dashboard
  (`POST /api/projects`, `NewProjectModal`); `foreman run` from dashboard
  (`POST /api/projects/{id}/agent/start`, subprocess spawn, Run/Stop toggle)
- completed `sprint-34-task-edit-enforcement`
- `update_task_fields` tracks changed fields; `human.task_edited` event emitted
  for `in_progress`/`blocked` task edits; `getEventCategory` broadened to
  `human.*` prefix; synthetic run created when task has no run history
- completed `sprint-35-dashboard-crud-polish`
- board-view filter leak fixed (filters gated on list mode); delete task/sprint
  with FK-safe cascade in store; sprint title inline editing; sprint ordering
  (`order_index` in API, ↑/↓ reorder buttons); `started_at`/`completed_at`
  exposed in sprint responses; date display on cards and sprint header
- completed `sprint-36-intervention-and-ordering`
- sprint list ordering fixed: active/completed sprints above planned; stop
  individual task (`POST /api/tasks/{id}/stop`) with Stop button on cards and
  drawer; Cancel sprint button in sprint view header for active and planned
  sprints; board column equal-width fix; custom scrollbar styling; duplicate
  branch name generation fixed in orchestrator

## Previously completed (sprints 1–29)

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
- completed `sprint-28-autonomous-task-selection`
- implemented `task_selection_mode="autonomous"` in `ForemanOrchestrator`:
  `select_next_task()` dispatches to `_select_next_task_autonomous()` which
  resumes in-progress tasks first, then creates placeholder tasks up to a
  per-sprint `max_autonomous_tasks` limit (default 5, configurable via project
  settings)
- the placeholder task (`created_by="orchestrator"`, `title="[autonomous] new
  task"`) is persisted to SQLite; the agent populates it via the existing
  `signal.task_started` handler
- 8 new tests in `AutonomousTaskSelectionTests`; 204 non-E2E tests pass total
- completed `sprint-29-db-migrate-cli`
- added `foreman db version` — reports current schema version; warns when
  `schema_migrations` table is absent (pre-migration-framework databases)
- added `foreman db migrate` — calls `store.initialize()` (idempotent); reports
  each applied migration with version number and description, or confirms the
  schema is already up to date
- changed `ForemanStore.initialize()` to return `list[int]` (applied migration
  versions); backward-compatible since callers ignored the prior `None` return
- 7 new tests in `DbCommandTests`; 203 non-E2E tests pass total
- completed `sprint-31-backlog-items`
- sprint creation modal now accepts inline task entries; tasks are created
  atomically with the sprint via `initial_tasks` in the API body
- task cancellation: `POST /api/tasks/{id}/cancel` + Cancel task button in the
  detail drawer; rejects done/already-cancelled tasks with 400
- task dependencies: `depends_on_task_ids` now included in `get_task()` response;
  detail drawer renders a Dependencies section with chips
- event log load-more: `before_event_id` cursor in store and service; `has_more`
  flag on all `list_sprint_events` responses; "Load older events" button in UI
- cancelled sprint filter: added to `STATUS_FILTER_OPTIONS`; kanban Done column
  includes cancelled sprints
- 8 new tests in `DashboardSprintTaskBacklogTests`; 221 non-E2E, 20 E2E tests
- completed `sprint-30-wire-dead-surfaces`
- wired `Stop agent` button to `POST /api/projects/{id}/agent/stop`; blocks all
  in-progress tasks in the active sprint and emits `human.stop_requested` events
- added `PATCH /api/sprints/{sprint_id}` endpoint with valid lifecycle transitions
  (planned→active, active→completed/cancelled); sets `started_at`/`completed_at`
- added `PATCH /api/tasks/{task_id}` endpoint for `description` and `priority`
  field updates; unknown fields rejected with 400
- extended run serialization in `get_task()` to include `session_id`,
  `branch_name`, `started_at`, `completed_at`
- exposed `description` and `priority` in `get_task()` and `list_sprint_tasks()`
  responses; task detail drawer shows both when non-default
- added sprint status badge + Start/Complete sprint buttons to sprint view header
- added Start/Complete/Cancel action buttons to sprint list cards
- fixed two E2E test regressions from previous dashboard overhaul session
- 10 new tests in `DashboardSprintLifecycleTests`; 213 non-E2E, 20 E2E tests pass

## Current repo state (as of sprint-35)

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
  - full dashboard CRUD: create, edit, and delete for projects, sprints, and
    tasks; sprint title and goal inline editing; sprint ordering via ↑/↓ with
    `order_index` in all sprint API responses; `started_at`/`completed_at`
    displayed on sprint cards and in sprint view header,
  - `human.task_edited` event emission for in-progress and blocked task edits,
    with synthetic run creation when no run history exists,
  - 95 dashboard unit/integration tests and 20 E2E tests all passing,
  - repo-memory docs that are intended to let a fresh agent continue from the
    next slice without reconstructing prior branch history.
- The temporary markdown sprint and status workflow remains intentional
  bootstrap state. The eventual product should move operational state into
  SQLite as described in the spec.

## Ready next

- SSE transport hardening (Tier 3, deferred — lowest urgency)
- E2E test coverage for sprints 32–35 features
- Task reordering within sprint board (order_index UI for tasks)
- Task priority editing UI
- Move task between sprints
- See `docs/sprints/backlog.md` for full list

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
- `task_selection_mode="autonomous"` is now implemented; the agent must emit
  `signal.task_started` to populate placeholder tasks or they remain with the
  default title.
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
