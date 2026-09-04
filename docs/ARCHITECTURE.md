# Architecture

## Status

- Status: integrated pre-release baseline
- Primary source: `docs/specs/engine-design-v3.md`
- UI reference: `docs/mockups/foreman-mockup-v6.html`
- ADRs:
  - `docs/adr/ADR-0001-runner-session-backend-contract.md`
  - `docs/adr/ADR-0002-dashboard-data-access-boundary.md`
  - `docs/adr/ADR-0003-web-ui-api-boundary.md`
  - `docs/adr/ADR-0004-dashboard-backend-framework.md`

This document records the active architectural baseline for Foreman as it
exists after reconciling the completed feature branches. It documents the
constraints the code now depends on, the structural debt that is explicitly
being corrected, and the gaps the next sprint is expected to close.

## Product identity

Foreman is an autonomous development engine that:

- stores structured project state in SQLite,
- projects ephemeral runtime context into a gitignored repo path,
- drives delivery through declarative roles and workflows,
- records runs and events for later inspection,
- exposes state through both CLI and dashboard surfaces.

It is not just a wrapper around one coding agent. The wrappers in `scripts/`
remain bootstrap tooling, not the product architecture.

## Core layers

The spec defines four layers that should remain explicit:

1. Agent Runner
2. Role System
3. Workflow Engine
4. Orchestrator

The current codebase maps closely onto that split:

- `foreman/store.py` and `foreman/models.py` own persisted state,
- `foreman/roles.py` and `foreman/workflows.py` own declarative configuration,
- `foreman/orchestrator.py` owns workflow execution and durable transitions,
- `foreman/runner/` owns backend-specific transport and event normalization,
- `foreman/cli.py`, `foreman/dashboard_runtime.py`,
  `foreman/dashboard_service.py`, `foreman/dashboard_backend.py`, and
  `frontend/` expose inspection and control surfaces.

## Source of truth

Foreman's runtime source of truth is SQLite.

Primary persisted entities:

- projects
- sprints
- tasks
- runs
- events

Committed markdown in this repository is still temporary bootstrap memory.
Once Foreman matures, files like `docs/STATUS.md` and `docs/sprints/current.md`
should become planning artifacts or projections rather than operational state.
That bootstrap memory status does not relax implementation quality standards
for product code.

## Runtime repo boundary

The runtime repo integration remains intentionally narrow:

- generated `AGENTS.md`
- `docs/adr/`
- gitignored `.foreman/`

Per the spec, convention docs such as branching and testing should eventually
be generated or projected rather than treated as the product database.

## Implemented seams

### Store and workflow state

The repository now ships:

- typed models and a currently bootstrap SQLite schema for projects, sprints,
  tasks,
  runs, and events,
- query helpers for project status, sprint board state, run totals, and recent
  event slices,
- store-backed pruning of old `events` rows by project and cutoff while
  preserving blocked and in-progress task history,
- persisted workflow step, carried-output, and human-gate resume state on
  tasks and runs.

### Roles, workflows, and orchestration

Foreman now has:

- shipped `roles/*.toml` and `workflows/*.toml` defaults,
- prompt rendering with completion and signal conventions,
- a persisted orchestrator loop that can execute the shipped workflow graph,
- end-to-end runtime coverage for the opt-in `development_secure` variant
  through code review, security review, test, and merge,
- built-ins for tests, merge, mark-done, human-gate pause or resume, and
  runtime context projection.

### Native runner boundary

ADR-0001 is now the active contract for native backends.

The current runtime supports:

- Claude Code via `stream-json`,
- Codex via `codex app-server` JSON-RPC,
- explicit non-retryable backend preflight before `agent.started`,
- normalized event capture into Foreman `events`,
- role-level approval policy and disallowed-tool handling,
- role-level `[agent.env]` injection for Anthropic-compatible endpoints such
  as MiniMax M3 through the existing Claude Code harness,
- persisted `session_id`, `token_count`, `cost_usd`, and `duration_ms`.

### Resident engine and the project engine lock

ADR-0011 is the active contract for engine residency and concurrency.

- `foreman/engine_lock.py` — `EngineLock`, a lease-backed context manager
  (`resource_type="engine"`, `resource_id=<project id>`) that enforces one
  engine per project. Both `foreman run` and `foreman serve` hold it for the
  duration of their work; a second engine is refused with the holder named.
  Renewal runs on a daemon timer thread with its **own** `ForemanStore`
  connection, deliberately independent of agent output.
- `foreman/serve.py` — `ResidentEngine`, the loop: one `run_project` pass per
  iteration, an idle wait on `PRAGMA data_version` or the poll interval,
  per-task failure isolation with a doubling backoff, and a clean SIGTERM stop.
  `serve_project()` composes the lock and the loop; the CLI handler stays thin
  (arguments, exit codes, messages) and the loop is unit-testable without a
  subprocess.
- `foreman/logs.py` — JSON-lines process logging on stderr. The resident engine
  has no terminal, so this is its operator surface; the orchestrator mirrors
  every persisted event to the same logger, at the level
  `event_log_level()` assigns its family (narrative at INFO, agent output
  firehose at DEBUG).
- Orchestrator support: `run_project(maintenance=...)` keeps retention pruning
  and crash recovery off idle wakes, `TaskExecutionError` tags a failure with
  its task id, and `block_task_for_error()` parks a task through the existing
  system-run and `engine.attention_needed` path.

### Inspection and dashboard surfaces

Foreman now exposes two first-class observation surfaces:

- CLI inspection commands: `board`, `history`, `cost`, and live `watch`
- a dashboard service layer in `foreman/dashboard_service.py`, a FastAPI
  transport layer in `foreman/dashboard_backend.py`, a React frontend
  workspace in `frontend/`, and a runtime entrypoint in
  `foreman/dashboard_runtime.py`

Per ADR-0002, the dashboard currently reads directly from `ForemanStore`
read-model helpers rather than going through a separate query service or
projection database.

Per ADR-0003, the product direction is now:

- backend modules expose the dashboard through explicit JSON and streaming API
  boundaries,
- a dedicated React frontend owns web UI rendering and client state,
- embedding substantial product UI markup inside backend Python modules is
  treated as debt to remove, not as an acceptable steady-state design.

Per ADR-0004, the product backend transport for the dashboard is now:

- FastAPI for routing and HTTP behavior,
- uvicorn for the runtime server boundary,
- `dashboard_service.py` as the store-backed service layer under those routes,
- `dashboard_runtime.py` as the product runtime entrypoint and asset or
  frontend-dev launcher for `foreman dashboard`.

The current dashboard baseline includes:

- extracted backend responses for project, sprint, task, action, and
  streaming contracts in `foreman/dashboard_service.py`,
- FastAPI route delivery in `foreman/dashboard_backend.py`,
- a dedicated React and Vite frontend source workspace in `frontend/`,
- built frontend assets in `foreman/dashboard_frontend_dist/`,
- Vite dev-mode `/api` proxying plus a combined local dashboard dev launcher
  in `scripts/dashboard_dev.py`,
- project overview and multi-project switching,
- a queue-oriented project view with Active, Queue, and Archive sections,
- sprint board grouped by task status,
- task detail with run history, acceptance criteria, and step visit counts,
- activity feed filtering,
- decision-gate banners and resolution actions,
- human message submission stored as `human.message` events,
- a per-project meta-agent sidebar backed by a persistent Claude Code session,
- a dedicated sprint event stream for incremental persisted activity delivery,
- debounced board and selected-task refresh on incoming activity,
- approve or deny actions that call the orchestrator to resume workflow
  execution.

The current implementation debt in this area is explicit:

- the committed built frontend assets must stay synchronized with the source
  app in `frontend/`,
- browser-driven dashboard E2E coverage now exists, but newer surfaces still
  need more coverage, especially the meta-agent panel and recent queue or
  editing flows,
- the SSE transport still polls SQLite directly inside the FastAPI stream
  loop.

The current CLI watch baseline now includes:

- project tails that resolve the active sprint at startup and fall back to
  project-wide activity when no sprint is active,
- explicit sprint tails for one sprint's persisted activity,
- explicit run tails for one run's persisted activity,
- incremental cursor-based delivery from SQLite rather than repeated
  snapshot rendering.

## Current runtime constraints worth preserving

- Every workflow step persists a `runs` row, including built-ins, so workflow
  and engine events always have a durable `run_id`.
- The orchestrator uses synthetic orchestrator runs for control-path events
  such as loop limits and crash recovery because the current schema requires
  `events.run_id` to be non-null.
- The shipped workflow TOML treats `_builtin:mark_done` as a terminal step with
  no outgoing edge, so the runtime treats `task.status == "done"` as
  successful workflow termination instead of a fallback block.
- `foreman init` never overwrites a repo's existing `AGENTS.md`; generated
  instructions remain a one-time scaffold that the user owns afterward.
- Repo-local CLI discovery uses a hidden `.foreman.db` file and walks up from
  the current working directory to find an existing database.
- `foreman init` defaults to `<repo>/.foreman.db`, and scaffolded repos keep
  that file gitignored.
- `--db PATH` remains the explicit override for alternate stores and
  out-of-repo inspection.
- secure workflow selection is currently explicit at project init time via
  `workflow_id`, including `foreman init --workflow development_secure`.
- Deferred human-gate resume is represented by an `in_progress` task whose
  `workflow_current_step` points at the next step to execute.
- Immediate human-gate resume re-checks out the task branch before native
  execution, while still deferring safely when the next backend or repo
  runtime is unavailable.
- backend preflight failures now fail once before `agent.started`, while
  post-start transport and process failures remain retryable infrastructure
  errors.
- the dashboard is loopback-only by default; a network bind requires a shared
  token checked on every `/api` route, CORS is allowlist-only, the manager
  chat is disabled off-loopback unless explicitly allowed, and project paths
  must be existing git repositories (optionally under configured roots).
  Per-user identity replaces the shared token in Phase 1.
- every shipped workflow tests before it reviews and ends in a
  `merge_approval` human gate; gate steps carry a `policy` resolved from a
  per-task override, then the project setting, then a default, and an `auto`
  policy produces a run row, an event, and a `policy:<name>` decision record.
- the role contract (completion marker or verdict) is read from the agent's
  final message only; decision roles declare `outcomes`, `review_kind`, and
  allowed `signals` in TOML, and the orchestrator, workflow validator, and
  evidence builder read those declarations instead of role ids.
- every agent and test process runs through `foreman/runner/process.py`:
  pumped streams, wall-clock ticks while the child is silent, its own
  session, process-group termination, and a registry drained on SIGTERM,
  SIGINT, and exit; `EngineShutdown` and `LeaseLostError` settle the active
  run as `killed` and leave the task at its persisted resume point.
- file-backed stores run in WAL mode with a 30 s busy timeout and retrying
  hot writes so the engine, dashboard, and CLI can share one database file;
  migrations apply atomically per version inside `BEGIN IMMEDIATE`.
- gate decisions and decision gates carry `ON DELETE` rules (migration 14),
  and store deletes are dependent-aware, so retention and deletion never
  violate a foreign key; a pruned run leaves its gate decision with a null
  run link.
- task keys come from a per-project sequence bumped inside the insert
  transaction and are unique per project by index.
- project settings are validated through `ProjectSettings` at the start of
  every run, at the dashboard settings endpoint, and at `foreman config
  --set`; event, run, and prompt retention are opt-in.
- `event_retention_days` prunes old project events on startup when set, but current
  schema constraints force `engine.event_pruned` to ride on a synthetic
  task-bound orchestrator run instead of a pure project-level event.
- product-facing CLI surfaces now ship as explicit commands rather than a
  generic stub handler.
- `task_selection_mode="autonomous"` now creates placeholder tasks within the
  active sprint, while `autonomy_level` separately governs sprint-to-sprint
  advancement behavior.
- `session_persistence` is a role-level policy with scope `task + role +
  backend`, and fresh orchestrator invocations now reload the last compatible
  persisted session from SQLite for persistent roles.
- Codex token usage is persisted accurately, but the current app-server
  contract does not expose USD pricing, so Codex `cost_usd` remains zero.
- Third-party Claude Code endpoints should use distinct `CLAUDE_CONFIG_DIR`
  values in `[agent.env]` so persisted session ids do not cross provider
  boundaries.
- the dashboard live transport currently uses server-sent events through the
  FastAPI backend, with store polling inside the stream loop and the
  extracted `foreman.dashboard_service` layer acting as the service boundary
  under the shipped React frontend.
- `foreman watch` now shares the dashboard's persisted-event cursor boundary
  but stays on a direct store-read loop instead of going through the HTTP SSE
  transport.
- `.foreman/status.md` still emits an explicit open-decisions placeholder
  because the SQLite schema does not yet persist decision records.

## 2026 tightening items (Items 1–23)

The following items were implemented as hardening before the 1.0 release:

**Lease-based concurrency control (Items 1–3)**
- `leases` table with one active lease per `(project_id, resource_type, resource_id)`
- `holder_id` and `lease_token` provide ownership verification
- `fencing_token` increments on reacquisition after expiry
- Orchestrator acquires lease before executing a task and renews between steps
- Stale running run recovery is lease-aware (only expired/missing leases trigger recovery)
- Active leases are projected into `.foreman/context.md` without the secret token

**Branch enforcement (Item 4)**
- `git.py` exposes `head_sha`, `branch_exists`, `worktree_branch`, `assert_not_on_default_branch`, `assert_default_branch_unchanged`
- Before every agent step: default branch HEAD is captured; task branch is checked out
- After every agent step: default branch HEAD must not have changed unless `_builtin:merge`
- `engine.branch_violation` is emitted on invariant failure

**Autonomous contract (Item 5)**
- After the first developer step in autonomous mode, `signal.task_started` is required
- Missing signal emits `workflow.autonomous_contract_missing` and blocks the task

**Signal validation (Items 6–7)**
- `foreman/runner/signals.py` now emits `signal.invalid` or `signal.unknown` instead of silently dropping bad signals
- `signal.task_created` assigns `order_index` from `store.next_task_order_index()` and emits `engine.task_created`

**Outcome normalization (Item 8)**
- `foreman/outcomes.py` defines canonical constants: DONE, CANCELLED, BLOCKED, SUCCESS, FAILURE, ERROR, KILLED, PAUSED, APPROVE, DENY, STEER
- All orchestrator step results and reviewer decisions are normalized before transition lookup

**Completion evidence (Items 9–10, 18)**
- `CompletionEvidence` expanded with git SHAs, commit count, structured test record, proof_status, criteria_checklist, failure_reasons
- `_builtin:merge` calls `merge_preflight` and gates on `proof_status` before attempting merge
- the legacy `finalize_supervisor_merge` path was removed in sprint 53; the only completion path is `_builtin:mark_done` + `_builtin:merge`

**Versioned event schema (Item 12)**
- `foreman/events.py` provides typed event constructors with `schema_version` in every payload

**Cost and time gates (Item 13)**
- Task-level time gate enforced before each workflow step with `gate.time_exceeded` event
- Cost gate was already present

**Role policy audit (Item 15)**
- `engine.role_policy` emitted before every agent step: backend, permission_mode, disallowed_tools

**Human gate decisions (Item 16)**
- `human_gate_decisions` table (migration 7) persists every approve/deny/steer with task_id, workflow_step, decided_by, run_id

**Workflow validation (Item 17)**
- `WorkflowDefinition.validate()` checks duplicate transition triggers, non-terminal step coverage, builtin outcome validity
- Called at workflow load time

**Settings validation (Item 20)**
- `foreman/settings.py` provides `ProjectSettings.from_raw()` with per-field validation
- Invalid project settings raise `SettingsError` at parse time

**Context projection (Item 21)**
- `.foreman/context.md` includes workflow step, active lease metadata (without token), and autonomous signal contract reminder

**Failure classification (Item 22)**
- `Run.failure_type` column (migration 8) classifies failures: preflight, infrastructure, policy, gate, workflow

**Merge preflight (Item 23)**
- `git.merge_preflight()` validates source exists, target exists, worktree clean, source != target, source has commits ahead
- `_builtin:merge` runs full preflight before attempting merge

**Bootstrap scripts (Item 19)**
- `scripts/reviewed_claude.py` and `scripts/reviewed_codex.py` were deprecated here and removed in sprint 53
- `foreman run` and `foreman serve` are the only autonomous entry points, and
  both hold the per-project engine lock (ADR-0011)

## Next architectural slice

The resident engine (ADR-0011) makes the dashboard's "spawn a `foreman run`
subprocess" pattern the odd one out: it now competes for the engine lock rather
than cooperating with the resident worker. The next slice replaces it with an
engine command table the dashboard and CLI write to and the resident engine
consumes, plus reporting for tasks the engine has dead-lettered into `blocked`.
