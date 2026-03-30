# Architecture

## Status

- Status: integrated pre-release baseline
- Primary source: `docs/specs/engine-design-v3.md`
- UI reference: `docs/mockups/foreman-mockup-v6.html`
- ADRs:
  - `docs/adr/ADR-0001-runner-session-backend-contract.md`
  - `docs/adr/ADR-0002-dashboard-data-access-boundary.md`

This document records the active architectural baseline for Foreman as it
exists after reconciling the completed feature branches. It documents the
constraints the code now depends on and the gaps the next sprint is expected
to close.

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
- `foreman/cli.py` and `foreman/dashboard.py` expose inspection and control
  surfaces.

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

- typed models and a bootstrap SQLite schema for projects, sprints, tasks,
  runs, and events,
- query helpers for project status, sprint board state, run totals, and recent
  event slices,
- persisted workflow step, carried-output, and human-gate resume state on
  tasks and runs.

### Roles, workflows, and orchestration

Foreman now has:

- shipped `roles/*.toml` and `workflows/*.toml` defaults,
- prompt rendering with completion and signal conventions,
- a persisted orchestrator loop that can execute the shipped workflow graph,
- built-ins for tests, merge, mark-done, human-gate pause or resume, and
  runtime context projection.

### Native runner boundary

ADR-0001 is now the active contract for native backends.

The current runtime supports:

- Claude Code via `stream-json`,
- Codex via `codex app-server` JSON-RPC,
- normalized event capture into Foreman `events`,
- role-level approval policy and disallowed-tool handling,
- persisted `session_id`, `token_count`, `cost_usd`, and `duration_ms`.

### Inspection and dashboard surfaces

Foreman now exposes two first-class observation surfaces:

- CLI inspection commands: `board`, `history`, `cost`, and bounded `watch`
- a dashboard web surface in `foreman/dashboard.py`

Per ADR-0002, the dashboard currently reads directly from `ForemanStore`
read-model helpers rather than going through a separate query service or
projection database.

The current dashboard baseline includes:

- project overview and multi-project switching,
- sprint board grouped by task status,
- task detail with run history, acceptance criteria, and step visit counts,
- activity feed filtering,
- human message submission stored as `human.message` events,
- approve or deny actions that call the orchestrator to resume workflow
  execution.

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
- The bootstrap CLI still requires explicit `--db PATH` selection for
  SQLite-backed lifecycle, inspection, monitoring, and human-gate commands.
- Deferred human-gate resume is represented by an `in_progress` task whose
  `workflow_current_step` points at the next step to execute.
- Immediate human-gate resume re-checks out the task branch before native
  execution, while still deferring safely when the next backend or repo
  runtime is unavailable.
- `session_persistence` is a role-level policy with scope `task + role +
  backend`, but fresh orchestrator invocations do not yet reload the last
  compatible session from SQLite. That is the active implementation gap from
  ADR-0001.
- Codex token usage is persisted accurately, but the current app-server
  contract does not expose USD pricing, so Codex `cost_usd` remains zero.
- `foreman watch` and the dashboard activity feed still rely on bounded polling
  rather than a dedicated streaming transport.
- `.foreman/status.md` still emits an explicit open-decisions placeholder
  because the SQLite schema does not yet persist decision records.

## Next architectural slice

The next slice should close the cross-invocation session-reuse gap from
ADR-0001:

- add a store query for the last compatible persisted session,
- teach the orchestrator to reuse it for persistent roles on fresh process
  starts,
- keep non-persistent roles starting fresh,
- cover Claude Code, Codex, and human-gate resume in tests.
