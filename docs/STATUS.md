# STATUS

## Current sprint

- Sprint: `sprint-15-engine-db-discovery`
- Status: active
- Goal: remove the bootstrap requirement to pass explicit `--db` paths for
  normal SQLite-backed CLI flows

## Active branches

- no long-lived feature branch should remain loose after the dashboard
  streaming slice; start sprint-15 work from `main`

## Completed this week

- reconciled the previously loose feature and recovery histories into one
  integrated mainline and pushed the result to `origin/main`
- completed `sprint-13-persistent-session-reload`
- implemented cross-invocation native session reuse for persistent roles by
  reloading the latest compatible `session_id` from SQLite
- completed `sprint-14-dashboard-streaming-transport`
- added a dedicated dashboard sprint event stream with incremental persisted
  event delivery
- switched the dashboard activity panel to a live subscription path and
  debounced task-state refresh on incoming events
- moved the dashboard server to a threaded HTTP boundary so long-lived
  activity streams do not block approve or deny or message requests

## Current repo state

- The repository now contains:
  - the product spec and UI mockup,
  - the `foreman` package with SQLite-backed models, store, loaders, CLI, and
    orchestrator,
  - runtime `.foreman/context.md` and `.foreman/status.md` projection from
    SQLite,
  - persisted human-gate approval and denial commands with deferred or
    immediate native resume behavior,
  - native Claude Code and Codex runners with structured event capture,
    approval-policy handling, retry normalization, and persisted session reuse
    across fresh orchestrator invocations for persistent roles,
  - monitoring CLI surfaces for board, history, cost, and bounded watch
    snapshots,
  - accepted ADRs for runner session semantics and dashboard data access,
  - a dashboard web surface with project overview, sprint board, task detail,
    activity feed, human message input, activity filtering, project switching,
    approve or deny actions that resume the workflow, and a dedicated sprint
    event stream that keeps activity current without full-list polling,
  - unit and integration coverage across store, CLI, orchestrator, runners,
    dashboard, and executor seams,
  - repo-memory docs that are intended to let a fresh agent continue from the
    next slice without reconstructing prior branch history.
- The temporary markdown sprint and status workflow remains intentional
  bootstrap state. The eventual product should move operational state into
  SQLite as described in the spec.

## Ready next

1. add engine-level database discovery for repo-local CLI usage
2. keep explicit `--db` as a deterministic override while normal flows resolve
   the active engine database automatically
3. document how database discovery interacts with init, monitoring, and
   human-gate resume commands

## Open risks

- `reviewed_codex.py` and `reviewed_claude.py` are bootstrap supervisors, not
  the Foreman product itself; their behavior should not accidentally become the
  long-term architecture.
- The bootstrap CLI still requires explicit `--db PATH` selection for
  SQLite-backed lifecycle, inspection, monitoring, and human-gate commands
  because engine-instance configuration does not exist yet.
- `foreman watch` still relies on bounded polling snapshots even though the
  dashboard now uses a dedicated live event stream.
- The native Claude and Codex runners assume working `claude` and `codex`
  executables in PATH and currently rely on runtime process errors rather than
  explicit preflight health checks.
- The Codex app-server protocol exposes token usage but not USD pricing, so
  Codex runs currently persist `token_count` accurately while `cost_usd`
  remains `0.0`.
- The SQLite layer still uses bootstrap DDL without a migration framework.

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
  resuming workflow execution. The current runtime does that when the next
  backend and repo are available, but it still persists a deferred next step
  when the resumed workflow cannot execute safely yet.
- The spec describes `foreman watch` as a live event tail. The current
  bootstrap CLI still renders bounded polling snapshots, while the dashboard
  now uses a dedicated event stream for live activity.

## Open decisions

- whether `foreman watch` should converge on the dashboard's dedicated
  streaming transport or remain a separate CLI-tail implementation
- whether project `default_model` should be validated against the selected
  backend instead of being passed through verbatim at runtime
- whether engine-level database discovery should replace the current explicit
  `--db` requirement
- whether the security review flow should be implemented as a separate shipped
  workflow or as a parameterized branch of the default workflow
