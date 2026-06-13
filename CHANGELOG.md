# Changelog

All notable changes to this repository should be documented here.

The repo is still pre-release, so entries currently track milestone and repo
memory changes rather than versioned product releases.

## [Unreleased]

### Milestone

- **Review roadmap complete (Phases 0–7).** The stacked review branches
  (Sprints 49–52) were fast-forwarded to `main` in order on 2026-06-13
  (`62c2e25` → `2ca7b49` → `b53f930` → `35b667c`) and the sprints archived under
  `docs/sprints/archive/`. Full suite: 571 tests passing.

### Frontend

- tied the React dashboard to the finished backend (see
  `docs/reviews/frontend-gap-analysis.md`): the task drawer now shows completion
  evidence (verdict / proof status / score / judged-by + per-criterion
  checklist) and the per-run model; an `engine.attention_needed` supervision
  banner runs one manager turn via `POST …/meta/supervise`; the settings panel
  binds to the real `ProjectSettings` (models/token-economy, criteria judge,
  cost/time gates, `completion_guard_enabled`) and can select
  `development_tiered`; new-task creation carries description, complexity, and
  dependencies.
- fixed frontend bugs: the new-task "Context" field was silently dropped; the
  Run/Stop toggle inferred agent state from task status instead of the
  authoritative `agent_running` field; the settings panel wrote inert keys and
  offered a Codex meta-backend option that broke the manager; the active-sprint
  header showed a dead "Stop" button when idle — it is now a Run↔Stop toggle so
  an idle sprint exposes a usable "Run".
- backend: `POST /api/sprints/{id}/tasks` (`create_task`) now accepts
  `description`, `complexity`, and `depends_on` (matching the CLI); `get_task`
  serializes `completion_evidence`.

### Fixed

- supervision now emits the full attention-trigger taxonomy: a completion/merge
  guard block whose proof gate failed raises `engine.attention_needed` with
  trigger `evidence_failed` (vs. the generic `task_blocked`), and a sprint that
  resolves while the engine stops (supervised/directed handoff, or no further
  work) raises trigger `sprint_resolved`. Previously only `task_blocked` and
  `loop_limit` were emitted, so two triggers defined in the digest never fired.

### Documentation

- added `docs/MANUAL.md`, a complete operator's guide (install, quickstart, CLI
  reference, roles/workflows, multi-model fleet, completion evidence + proof
  gate, tiered review, meta-agent + supervision, dashboard HTTP API, settings,
  event taxonomy, troubleshooting); README now points to it.
- added `docs/reviews/review-md-backend-audit.md`, the independent backend audit
  of the `review.md` implementation.

### Added

- supervision turns and transport polish (sprint 52, review Phases 6–7):
  `foreman/digest.py` `build_attention_digest`; an `engine.attention_needed`
  event emitted exactly once when a task transitions to blocked (loop-limit and
  signal-blocker paths tagged with their trigger); a
  `POST /api/projects/{id}/meta/supervise` endpoint that runs one
  `origin="supervision"` meta turn from the digest, gating mutation on
  `autonomy_level` and rejecting replayed events with 409;
  `ForemanStore.data_version()` with `data_version`-gated SSE and `foreman
  watch` polling (interval lowered to 0.25s); persisted `Run.retry_count` from
  `agent.infra_error` events; the token-economy project settings registered in
  `ProjectSettings`; and ADR-0010
- token-economy evidence and tiered review (sprint 51, review Phases 4–5):
  `foreman/judge.py` with the keyword heuristic as the single owner plus an
  opt-in cheap-model criteria judge (direct Anthropic-compatible HTTP call,
  head/tail diff truncation, heuristic fallback on any error);
  `CompletionEvidence.judged_by` surfaced in the `engine.completion_evidence`
  event; the new `escalate` reviewer outcome; `triage_reviewer` and
  `frontier_reviewer` roles; a `{completion_diff}` curated-diff prompt payload
  for decision roles (`review_diff_max_chars` setting); and the
  `development_tiered` workflow (develop → triage → escalate-to-frontier review)
- per-task executor overrides and a model-escalation ladder (sprint 50, review
  Phase 3): migration 12 (`executor_overrides_json`, `complexity` on tasks);
  `Task.executor_overrides`/`Task.complexity`; role `[agent] model_ladder`;
  the pure `resolve_step_model` model-resolution function wired into the
  workflow loop and native runner with a `workflow.model_selected` event per
  agent step; architect `complexity` persisted from `signal.task_created`;
  `foreman task add --complexity`; `foreman task override` CLI; and
  `executor_overrides` on the dashboard `PATCH /api/tasks/{id}` plus task
  payloads
- durable, store-backed meta-agent chat (sprint 49, review Phase 2): migration
  11 (`meta_sessions`, `meta_turns`); store methods for session/turn
  persistence and cursor paging; a compact `build_state_header()` snapshot
  rebuilt every turn; a first-turn operating contract; crash-safe assistant-turn
  persistence; a configurable `meta_agent_model` setting; `limit`/`before`/
  `has_more` paging on the meta history endpoint
- `foreman task add --description`, `--sprint SPRINT_ID`, and `--depends-on`
  (validated against tasks in the same project)
- Foreman-specific repo instructions in `AGENTS.md`
- active sprint and backlog docs for the first Foreman implementation slice
- repository templates for PR summaries, checkpoints, and sprint archives
- `pyproject.toml` and the initial `foreman/` package scaffold
- a runnable CLI shell covering the spec-aligned command surface
- typed SQLite models and a spec-shaped `foreman.store` persistence layer for
  projects, sprints, tasks, runs, and events
- shipped declarative `roles/*.toml` and `workflows/*.toml` defaults
- a persisted orchestrator loop plus explicit built-in execution seams
- repo-local `.foreman.db` discovery with explicit `--db` override support
- FastAPI, uvicorn, and HTTP client dependencies for the dashboard backend
- a dedicated React and Vite dashboard frontend workspace in `frontend/`
- `foreman init` defaulting to `<repo>/.foreman.db` for repo scaffold
  generation and persisted project initialization
- runtime context projection in `.foreman/context.md` and `.foreman/status.md`
- persisted human-gate approve and deny commands
- native Claude Code and Codex runners in `foreman/runner/`
- store-backed monitoring commands in `foreman.cli` for `board`, `history`,
  `cost`, and `watch`
- `docs/adr/ADR-0001-runner-session-backend-contract.md`
- `docs/adr/ADR-0002-dashboard-data-access-boundary.md`
- `foreman/dashboard.py` with dashboard HTML shell and direct JSON endpoints
- dashboard task detail, activity feed, human message input, activity filter,
  project switcher, and approve or deny actions
- a dedicated dashboard sprint event stream for incremental live activity
  updates
- native runner task-lease heartbeats during streamed Claude/Codex execution
- `foreman/executor.py` and `tests/test_executor.py`
- end-to-end runtime coverage for the opt-in `development_secure` workflow
  plus secure workflow initialization coverage in the CLI
- explicit native backend preflight validation for Claude Code and Codex
- spec-aligned event-retention pruning for old project events
- live-tail `foreman watch` support across project, sprint, and run scopes
- `docs/adr/ADR-0003-web-ui-api-boundary.md`
- `docs/adr/ADR-0004-dashboard-backend-framework.md`
- `docs/adr/ADR-0009-multi-model-endpoints-via-role-env.md`
- per-role `[agent.env]` resolution for native runner environment injection
- `roles/developer_worker.toml` as the sequential worker-model role example
- production-hardening audit and detour planning docs
- `foreman/dashboard_service.py` as the extracted dashboard service layer
- `foreman/dashboard_backend.py` as the FastAPI dashboard transport
- `scripts/dashboard_dev.py` as the combined local dashboard frontend and
  backend launcher
- `frontend/src/App.test.jsx` and the frontend bundle build validation path
- dashboard transition checkpoint notes while the embedded shell was being
  replaced
- `docs/checkpoints/react-dashboard-foundation.md`

### Removed

- obsolete `foreman/executor.py` and `tests/test_executor.py`; the orchestrator
  native runner path is the maintained execution surface

### Changed

- repurposed the transplanted project-memory docs from Apparatus to Foreman
- aligned the autonomous wrapper scripts and repo validation expectations with
  `docs/specs/engine-design-v3.md` and
  `docs/mockups/foreman-mockup-v6.html`
- completed `sprint-01-foundation`, `sprint-02-orchestrator`,
  `sprint-03-scaffold`, and `sprint-04-context-projection`
- completed `sprint-05-human-gates`, `sprint-06-claude-runner`, and
  `sprint-07-codex-runner`
- completed `sprint-08-monitoring-cli`, archived it, and advanced project
  memory to the runner session and backend ADR sprint
- completed `sprint-09-runner-session-backend-adr`, archived it, and advanced
  project memory to the dashboard implementation sprint
- completed `sprint-10-dashboard-implementation`, archived it, and advanced
  project memory to the multi-project dashboard polish sprint
- completed `sprint-11-multi-project-dashboard-polish`, archived it, and
  advanced project memory to the dashboard approve or deny integration sprint
- completed `sprint-12-dashboard-approve-deny-integration`, archived it, and
  advanced project memory to the persistent-session reload sprint
- completed `sprint-13-persistent-session-reload`, archived it, and advanced
  project memory to the dashboard streaming transport sprint
- completed `sprint-14-dashboard-streaming-transport`, archived it, and
  advanced project memory to the engine DB discovery sprint
- completed `sprint-15-engine-db-discovery`, archived it, and advanced project
  memory to the security review workflow sprint
- completed `sprint-16-security-review-workflow`, archived it, and advanced
  project memory to the native backend preflight sprint
- completed `sprint-17-native-backend-preflight-checks`, archived it, and
  advanced project memory to the event-retention pruning sprint
- completed `sprint-18-event-retention-pruning`, archived it, and advanced
  project memory to the watch live-tail alignment sprint
- completed `sprint-19-watch-live-tail-alignment`, archived it, and advanced
  project memory to the migration framework bootstrap sprint
- tightened repo instructions so bootstrap status no longer permits
  prototype-grade implementation decisions
- replanned the next work as a production-hardening detour covering dashboard
  API extraction, React frontend replacement, stub removal, and delayed
  migration work
- completed `sprint-21-dashboard-api-extraction`, archived it, and advanced
  project memory to the dashboard backend foundation sprint
- extracted dashboard reads, actions, and incremental stream payload assembly
  into `foreman/dashboard_api.py` while keeping the current shell functional
- completed `sprint-22-dashboard-backend-foundation`, archived it, and
  advanced project memory to the React dashboard foundation sprint
- replaced the raw dashboard stdlib server with a uvicorn-backed FastAPI
  backend while preserving the current shell and route surface
- completed `sprint-23-react-dashboard-foundation`, archived it, and advanced
  project memory to the product-surface hardening sprint
- replaced the embedded dashboard shell with a dedicated React frontend,
  built asset delivery, and frontend-aware dashboard validation
- pruned redundant dashboard transition checkpoint and PR-summary files now
  that sprint archives and the dedicated frontend checkpoint are the durable
  history
- renamed the dashboard runtime wrapper to `foreman/dashboard_runtime.py` and
  the extracted dashboard service layer to `foreman/dashboard_service.py`
- added frontend-dev support to `foreman dashboard`, Vite `/api` proxying for
  `npm --prefix frontend run dev`, and a one-command
  `npm --prefix frontend run dev:full` workflow
- removed the remaining `handle_stub` product-surface fallbacks by
  implementing the shipped `project`, `sprint`, `task`, `run`, and `config`
  CLI behaviors with direct store or orchestrator integration
- expanded CLI subprocess coverage around sprint activation and completion,
  task lifecycle operations, project inspection, config updates, and direct
  run invocation
- reconciled the loose feature and recovery branches into an integrated
  mainline candidate and restored missing repo-memory artifacts from the
  runner-session ADR branch
- closed the most visible product-surface gaps: settings panel, sprint
  creation, and task creation now run end-to-end from React components
  through FastAPI endpoints to SQLite persistence
- added 15 integration tests covering settings read/update validation, sprint
  creation, and task creation through both the service layer and FastAPI
  transport
- introduced an explicit schema migration framework in `foreman/migrations.py`
  and `foreman/store.py`: version-tracked migrations replace the old bootstrap
  DDL, `initialize()` now upgrades existing databases to the latest schema
  version automatically
- added `docs/adr/ADR-0005-schema-migration-strategy.md` documenting the
  append-only migration list, `schema_migrations` tracking table, and
  `ForemanStore.migrate()` / `schema_version()` API
- added `tests/test_migrations.py` with 17 tests covering migration list
  integrity, fresh install, idempotency on both in-memory and file databases,
  incremental upgrade from a partially-migrated store, and schema version
  accuracy
- added migration 2 (`idx_runs_project_completed`) enabling efficient run
  retention queries; `test_partial_db_upgraded_to_latest` now passes
- added `ForemanStore.prune_old_runs()` to hard-delete terminal runs and their
  cascaded events older than a cutoff while protecting blocked/in-progress tasks
- added `ForemanStore.strip_old_run_prompts()` to null out `prompt_text` on old
  terminal runs while preserving run records and telemetry
- expanded orchestrator startup pruning via `prune_old_history()` reading
  `run_retention_days` and `prompt_retention_days` project settings; emits
  `engine.run_pruned` and `engine.prompt_stripped` lifecycle events
- added `tests/test_run_retention.py` with 19 tests covering deletion,
  active-work protection, cascade event removal, and prompt stripping
- hardened active-run crash recovery so stale task leases are force-expired
  when a run is recovered and live holders are identified by recent lease
  heartbeats
- added browser-driven E2E dashboard validation via Playwright and Chromium:
  `tests/test_e2e.py` with 20 tests covering dashboard load, project and sprint
  navigation, task detail drawer, settings panel, sprint creation, and task
  creation end to end against a live FastAPI server and seeded SQLite database
- added `playwright` and `pytest-playwright` to `pyproject.toml` as optional
  `e2e` dependencies
- implemented `task_selection_mode="autonomous"` in `ForemanOrchestrator`:
  `select_next_task()` now dispatches to `_select_next_task_autonomous()` for
  autonomous projects; resumes in-progress tasks, then creates placeholder tasks
  up to the per-sprint `max_autonomous_tasks` limit (default 5)
- added 8 tests in `AutonomousTaskSelectionTests` covering placeholder creation,
  in-progress resume, no-sprint, limit enforcement, human-task exclusion,
  directed-mode unchanged, and unknown-mode error
- added `foreman db version` — shows current schema version; handles missing
  `schema_migrations` table on pre-migration-framework databases
- added `foreman db migrate` — applies pending schema migrations via
  `store.initialize()` and reports each applied version with description
- changed `ForemanStore.initialize()` to return `list[int]` (backward-compatible)
- added 7 tests in `DbCommandTests`
- completed `sprint-30-wire-dead-surfaces`: wired Stop agent button to
  `POST /api/projects/{id}/agent/stop`; added `PATCH /api/sprints/{id}` for
  lifecycle transitions (planned→active, active→completed/cancelled) with
  `started_at`/`completed_at` timestamps; added `PATCH /api/tasks/{id}` for
  `description` and `priority` updates; extended `get_task` run serialization;
  added sprint status badge and Start/Complete buttons in sprint view header;
  10 tests in `DashboardSprintLifecycleTests`
- completed `sprint-31-backlog-items`: sprint creation with inline initial tasks
  via `initial_tasks` in API body; task cancellation (`POST /api/tasks/{id}/cancel`,
  Cancel task button in drawer); task dependency display in drawer via
  `depends_on_task_ids`; event log load-more with `before_event_id` cursor and
  `has_more` flag; cancelled sprint filter in list and kanban Done column;
  8 tests in `DashboardSprintTaskBacklogTests`
- completed `sprint-32-tier1-editing`: task field editing in `TaskDetailDrawer`
  (title, type, acceptance criteria) via edit mode with chip selector and
  textarea; sprint goal inline editing in sprint header via `update_sprint_fields`;
  activity panel auto-scroll using `useLayoutEffect` and scroll-position tracking;
  `containerRef`/`onScroll` props on `EventList`; 11 tests in
  `DashboardTaskEditingTests`
- completed `sprint-33-tier2-gaps`: `workflow_current_step` added to
  `list_sprint_tasks` response and shown as badge on in-progress task cards and
  in detail drawer; project creation from dashboard via `POST /api/projects` and
  `NewProjectModal`; `foreman run` from dashboard via
  `POST /api/projects/{id}/agent/start` spawning a `foreman run` subprocess with
  double-start prevention; Run ▶ / Stop ■ toggle in sprint header; 9 tests in
  `DashboardTier2Tests`
- completed `sprint-34-task-edit-enforcement`: `update_task_fields` now tracks
  which fields actually changed; emits `human.task_edited` event with
  `changed_fields` payload for `in_progress` and `blocked` tasks; creates a
  synthetic dashboard/edit run if no run history exists (FK safety);
  `getEventCategory` broadened from exact `human.message` match to `human.*`
  prefix; `formatEventSummary` handles `human.task_edited`; 6 tests in
  `DashboardTaskEditEventTests`
- completed `sprint-35-dashboard-crud-polish`: fixed board-view filter leak
  (status filter buttons and sort conditioned on list view mode); added
  `ForemanStore.delete_task()` and `delete_sprint()` with FK-safe cascade
  (events → runs → tasks → sprint); `DELETE /api/tasks/{id}` and
  `DELETE /api/sprints/{id}` routes; delete buttons in `TaskDetailDrawer` and
  on sprint cards with confirm guard; sprint title inline editing in sprint
  header; `order_index`, `started_at`, `completed_at` added to all sprint API
  responses; `order_index` editable via `PATCH /api/sprints/{id}`; ↑/↓ reorder
  buttons on sprint cards swap adjacent `order_index` values; sprint list sort
  fixed to use `order_index` (was using undefined `order` field); `formatDate`
  added; dates shown on sprint cards and in sprint header stats; 18 new tests
  across `DashboardDeleteTests` and `DashboardSprintOrderTests`; 95 dashboard
  tests and 20 E2E tests all passing
- completed `sprint-36-intervention-and-ordering`: sprint list ordering fixed
  (active/completed above planned); `POST /api/tasks/{id}/stop` route for
  stopping individual in-progress tasks; Stop button on task cards and in
  task detail drawer; Cancel sprint button in sprint view header for active
  and planned sprints; board column equal-width fix (`minmax(0, 1fr)`);
  custom scrollbar styling; duplicate branch name generation fixed in
  orchestrator; 6 new tests in `DashboardInterventionTests`; 95 dashboard
  tests passing
