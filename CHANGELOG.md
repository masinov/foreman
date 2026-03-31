# Changelog

All notable changes to this repository should be documented here.

The repo is still pre-release, so entries currently track milestone and repo
memory changes rather than versioned product releases.

## [Unreleased]

### Added

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
- `foreman/executor.py` and `tests/test_executor.py`
- end-to-end runtime coverage for the opt-in `development_secure` workflow
  plus secure workflow initialization coverage in the CLI
- explicit native backend preflight validation for Claude Code and Codex
- spec-aligned event-retention pruning for old project events
- live-tail `foreman watch` support across project, sprint, and run scopes
- `docs/adr/ADR-0003-web-ui-api-boundary.md`
- `docs/adr/ADR-0004-dashboard-backend-framework.md`
- production-hardening audit and detour planning docs
- `foreman/dashboard_service.py` as the extracted dashboard service layer
- `foreman/dashboard_backend.py` as the FastAPI dashboard transport
- `scripts/dashboard_dev.py` as the combined local dashboard frontend and
  backend launcher
- `frontend/src/App.test.jsx` and the frontend bundle build validation path
- dashboard transition checkpoint notes while the embedded shell was being
  replaced
- `docs/checkpoints/react-dashboard-foundation.md`

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
