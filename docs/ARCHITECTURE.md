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
- persisted `session_id`, `token_count`, `cost_usd`, and `duration_ms`.

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
- sprint board grouped by task status,
- task detail with run history, acceptance criteria, and step visit counts,
- activity feed filtering,
- human message submission stored as `human.message` events,
- a dedicated sprint event stream for incremental persisted activity delivery,
- debounced board and selected-task refresh on incoming activity,
- approve or deny actions that call the orchestrator to resume workflow
  execution.

The current implementation debt in this area is explicit:

- there is still no browser-driven end-to-end dashboard test stack,
- the committed built frontend assets must stay synchronized with the source
  app in `frontend/`,
- the local Vite-plus-FastAPI development loop now exists, but it still lacks
  browser-driven end-to-end validation,
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
- `event_retention_days` now prunes old project events on startup, but current
  schema constraints force `engine.event_pruned` to ride on a synthetic
  task-bound orchestrator run instead of a pure project-level event.
- multiple product-facing CLI surfaces still route through a generic stub
  handler and must not be treated as complete.
- `task_selection_mode="autonomous"` is modeled in settings but is not yet
  implemented in the orchestrator.
- `session_persistence` is a role-level policy with scope `task + role +
  backend`, and fresh orchestrator invocations now reload the last compatible
  persisted session from SQLite for persistent roles.
- Codex token usage is persisted accurately, but the current app-server
  contract does not expose USD pricing, so Codex `cost_usd` remains zero.
- the dashboard live transport currently uses server-sent events through the
  FastAPI backend, with store polling inside the stream loop and the
  extracted `foreman.dashboard_service` layer acting as the service boundary
  under the shipped React frontend.
- `foreman watch` now shares the dashboard's persisted-event cursor boundary
  but stays on a direct store-read loop instead of going through the HTTP SSE
  transport.
- `.foreman/status.md` still emits an explicit open-decisions placeholder
  because the SQLite schema does not yet persist decision records.

## Next architectural slice

The next slice should harden the product surface now that the dashboard split
is in place:

- close the most visible dashboard and settings gaps exposed by the new
  frontend baseline,
- keep widening validation so the shipped CLI surface is exercised as real
  product behavior instead of placeholder wiring,
- add stronger product-surface validation above the current API and component
  layers.
