# STATUS

## Current sprint

- Sprint: `sprint-10-dashboard-implementation`
- Status: active
- Goal: build the first interactive dashboard slice aligned to the mockup
  using persisted Foreman project, sprint, task, run, and event state

## Active branches

- `feat/dashboard-shell` — land the first web dashboard shell with SQLite-backed
  project overview, sprint board, and activity feed

## Completed this week

- identified the true product inputs for this repo:
  `docs/specs/engine-design-v3.md` and
  `docs/mockups/foreman-mockup-v6.html`
- rewrote the transplanted Apparatus docs into Foreman-specific project memory
- initialized current sprint and backlog docs for the first implementation work
- aligned the autonomous wrapper scripts with the Foreman repo layout and
  product references
- updated repo validation to match the current scaffold
- added gitignore coverage for `.foreman/`, `.codex/`, and `.claude/`
- bootstrapped `pyproject.toml`, the `foreman/` package, and a spec-aligned CLI
  shell with smoke tests for `--help`, `projects`, and `status`
- fixed the reviewed Codex supervisor so an approved slice now triggers merge
  finalization and continuation instead of terminating the run after one task
- implemented typed SQLite-backed models and persistence for projects, sprints,
  tasks, runs, and events
- added round-trip store tests plus `foreman projects --db ...` and
  `foreman status --db ...` inspection support
- shipped declarative `roles/*.toml` and `workflows/*.toml` defaults from the
  spec examples
- implemented TOML-compatible role and workflow loaders, prompt rendering, and
  transition validation
- added `foreman roles` and `foreman workflows` plus dedicated loader tests
- completed `sprint-01-foundation` and rolled repo memory forward to
  `sprint-02-orchestrator`
- implemented the first real orchestrator loop against persisted tasks, runs,
  and events
- added explicit built-ins for tests, merge, mark-done, and human-gate pause
  behavior
- added git execution helpers plus integration tests that drive one task
  through the shipped development workflow, including review denial, test
  failure carry-output loops, and fallback blocking
- completed `sprint-02-orchestrator` and rolled repo memory forward to
  `sprint-03-scaffold`
- implemented `foreman.scaffold` with generated `AGENTS.md` rendering,
  idempotent `.gitignore` updates, and minimal target-repo scaffold creation
- added `foreman init --db <path>` so the CLI can create or update persisted
  projects directly in SQLite
- added scaffold generation coverage plus store lookup by repo path for
  re-initialization behavior
- completed `sprint-03-scaffold` and rolled repo memory forward to
  `sprint-04-context-projection`
- implemented `foreman.context` so runtime `.foreman/context.md` and
  `.foreman/status.md` are rendered from persisted SQLite state
- added `_builtin:context_write` plus orchestrator-triggered runtime context
  refresh before agent steps and after task completion
- added context projection unit and orchestrator integration coverage,
  including gitignored runtime files in temporary repo fixtures
- completed `sprint-04-context-projection` and rolled repo memory forward to
  `sprint-05-human-gates`
- implemented `foreman approve --db <path>` and `foreman deny --db <path>`
  against paused human-gate tasks in SQLite
- added persisted human-decision runs plus `workflow.resumed` events for
  approval and denial history
- taught the orchestrator to resume from a persisted workflow step instead of
  always restarting from workflow entry
- added bootstrap deferred resume semantics so human-gate decisions can record
  the next step and carried output even before native runners land
- expanded orchestrator and CLI coverage for human-gate pause, approve, deny,
  immediate resume, and deferred resume behavior
- completed `sprint-05-human-gates` and rolled repo memory forward to
  `sprint-06-claude-runner`
- implemented shared native runner primitives, structured signal extraction,
  and the first Claude Code stream-json backend
- taught the orchestrator to execute shipped Claude-backed roles through the
  native runner path when no scripted executor is injected
- added runner coverage for event mapping, retry normalization, developer
  session reuse, and native orchestrator execution
- completed `sprint-06-claude-runner` and rolled repo memory forward to
  `sprint-07-codex-runner`
- implemented the native Codex JSON-RPC runner through `codex app-server`
  with thread start or resume, streamed item mapping, and tool-approval
  responses
- taught the orchestrator to execute Codex-backed roles through the native
  runner path and to resume human-gate approvals immediately when the native
  backend and repo are available
- added Codex runner unit coverage plus orchestrator integration coverage for
  Codex success, review denial session reuse, and native human-gate resume
- completed `sprint-07-codex-runner` and rolled repo memory forward to
  `sprint-08-monitoring-cli`
- implemented store-backed `foreman board --db <path>`, `foreman history --db
  <path>`, `foreman cost --db <path>`, and `foreman watch --db <path>` for
  direct inspection of persisted sprint, run, and event state
- added monitoring read-model helpers for sprint-scoped task counts, cost
  aggregation, per-task run rollups, and recent event slices
- completed `sprint-08-monitoring-cli` and rolled repo memory forward to
  `sprint-09-runner-session-backend-adr`
- accepted `ADR-0001-runner-session-backend-contract` for session scope,
  workflow-versus-runner approval handling, and backend telemetry boundaries
- documented the current persistent-session reuse gap explicitly: session ids
  are persisted on runs, but fresh orchestrator invocations do not yet reload
  the last same-role session from SQLite
- completed `sprint-09-runner-session-backend-adr` and rolled repo memory
  forward to `sprint-10-dashboard-implementation`
- implemented `foreman.dashboard` with an HTTP server that serves the first
  dashboard HTML shell aligned to the mockup's project overview, sprint board,
  and activity feed hierarchy
- added JSON API endpoints for projects, sprints, tasks, and events so the
  dashboard can render persisted SQLite state instead of hardcoded demo data
- added `foreman dashboard --db <path>` CLI command to start the web server
- added dashboard unit tests for project status detection, API data access,
  and HTML content verification

## Current repo state

- The repository currently contains:
  - the product spec,
  - the UI mockup,
  - the initial `foreman` package scaffold and CLI shell,
  - a SQLite-backed store baseline with spec-shaped DDL and query helpers,
  - shipped default role and workflow definitions with loader validation,
  - a persisted orchestrator loop that can execute the shipped development
    workflow through agent and built-in steps,
  - a working `foreman init` path that scaffolds `AGENTS.md`, `docs/adr/`,
    `.foreman/`, and `.gitignore` updates in a target repo,
  - runtime `.foreman/context.md` and `.foreman/status.md` projection from
    SQLite before agent execution and after task completion,
  - persisted human-gate approval and denial commands with durable resume
    history and deferred-next-step support when no native runner is available,
  - the first native Claude Code runner with stream-json parsing, structured
    event mapping, infrastructure retries, and developer session reuse,
  - a native Codex runner with JSON-RPC thread start or resume, automatic
    approval handling, token-usage capture, and persistent thread reuse for
    Codex-backed roles,
  - store-backed monitoring CLI surfaces for board, history, cost, and
    bounded watch snapshots against persisted SQLite state,
  - an accepted ADR for runner session scope, approval policy, and backend
    contract boundaries,
  - immediate native human-gate resume when the next backend is available and
    the project repo exists, with deferred persistence retained for missing
    backends or missing repo paths,
  - the first web dashboard shell with project overview, sprint board, and
    activity feed views rendered from persisted SQLite state,
  - persisted project initialization and update behavior keyed by repo path,
  - smoke tests for the CLI bootstrap slice plus store, loader, and
    orchestrator, scaffold, context projection, Claude runner, Codex runner,
    and dashboard coverage,
  - regression coverage for the reviewed Codex supervisor flow,
  - the Codex and Claude supervisor scripts,
  - repo-memory docs that define the next engineering slices.
- The temporary markdown sprint and status workflow is intentional bootstrap
  state. The eventual product should move operational state into SQLite as
  described in the spec.

## Ready next

1. define the first ADR now that runner session handling and backend
   contracts are active runtime constraints
2. build the dashboard implementation aligned to the mockup
3. decide how live activity should graduate from polling CLI snapshots to a
   streaming dashboard transport

## Open risks

- `reviewed_codex.py` and `reviewed_claude.py` are bootstrap supervisors, not
  the Foreman product itself; their behavior should not accidentally become the
  long-term architecture.
- The package now has a real store, loader, orchestrator, project
  initialization path, human-gate resume commands, native Claude and Codex
  runners, and monitoring CLI surfaces, but the dashboard implementation is
  still missing.
- The bootstrap CLI currently requires explicit `--db PATH` selection for
  SQLite-backed lifecycle, inspection, monitoring, and human-gate commands
  because engine-instance configuration does not exist yet.
- `foreman watch` is currently a bounded polling view rather than the fully
  live event tail described in the spec, so terminal monitoring does not yet
  establish the eventual streaming transport boundary for the dashboard.
- The native Claude and Codex runners assume working `claude` and `codex`
  executables in PATH and currently rely on runtime process errors rather than
  explicit preflight health checks.
- The Codex app-server protocol exposes token usage but not USD pricing, so
  Codex runs currently persist `token_count` accurately while `cost_usd`
  remains `0.0`.
- editable installs are now validated with
  `./venv/bin/pip install -e . --no-build-isolation`, so fresh environments
  still need the repo venv to include the packaging toolchain declared in
  `pyproject.toml`.
- Python 3.10 support currently relies on a local TOML compatibility shim and a
  pip-vendored fallback during `--no-deps` validation installs.
- The SQLite layer currently uses bootstrap DDL without a migration framework;
  schema evolution rules still need an ADR once later slices depend on them.
- The UI mockup is static; implementing it will require decisions about API
  boundaries and event streaming that are not yet captured in ADRs.

## Documented conflicts

- The shipped workflow TOML treats `_builtin:mark_done` as a terminal step with
  no outbound transition, while the orchestrator pseudocode in the spec blocks
  any missing transition. The current implementation treats a step that sets
  task status to `done` as successful workflow termination and records that
  nuance here until the spec text is clarified.
- The spec's CLI examples omit explicit database selection, while the bootstrap
  CLI currently requires `--db PATH` for SQLite-backed init, inspection,
  monitoring, and human-gate commands because engine-level DB discovery has
  not been implemented yet.
- The spec expects `.foreman/status.md` to list open decisions, but the current
  SQLite schema has no structured decision records yet. The runtime projection
  currently emits an explicit placeholder until those records exist.
- The spec describes `foreman approve` and `foreman deny` as immediately
  resuming workflow execution. The current runtime now does that for both
  Claude-backed and Codex-backed next steps when a native runner is available
  and the repo path exists, but it still persists a deferred next step when
  the resumed workflow cannot execute safely yet.
- The spec describes `foreman watch` as a live event tail, while the current
  implementation intentionally renders bounded polling snapshots with
  `--iterations` and `--interval` until a streaming transport boundary exists.

## Open decisions

- whether the initial web surface should be delivered as static HTML plus JSON
  endpoints or as a richer app shell from the start
- how much of the current wrapper logic should survive once native Foreman
  runners exist
- whether the live dashboard activity surface should share the same transport
  model as `foreman watch` or move directly to a dedicated streaming channel
- whether project `default_model` should be validated against the selected
  agent backend instead of being passed through verbatim at runtime
- whether the shipped role pack should stay Claude-first or grow a parallel
  Codex-native default role set now that both backends exist
