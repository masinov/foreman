# STATUS

## Current sprint

- Sprint: `sprint-14-dashboard-streaming-transport`
- Status: active
- Goal: replace polling-only dashboard refresh with an explicit live event
  transport that keeps the activity feed and task state current

## Active branches

- no long-lived feature branch should remain loose after the session
  continuity slice; start sprint-14 work from `main`

## Completed this week

- reconciled the previously loose feature and recovery histories into one
  integrated mainline and pushed the result to `origin/main`
- restored the missing sprint-09 runner-session ADR artifacts and archived
  sprints 09 through 12
- completed `sprint-13-persistent-session-reload`
- implemented cross-invocation native session reuse for persistent roles by
  reloading the latest compatible `session_id` from SQLite
- added regression coverage for fresh-process Claude Code and Codex session
  reuse plus the negative case for non-persistent reviewer sessions

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
    and approve or deny actions that resume the workflow,
  - unit and integration coverage across store, CLI, orchestrator, runners,
    dashboard, and executor seams,
  - repo-memory docs that are intended to let a fresh agent continue from the
    next slice without reconstructing prior branch history.
- The temporary markdown sprint and status workflow remains intentional
  bootstrap state. The eventual product should move operational state into
  SQLite as described in the spec.

## Ready next

1. add a live dashboard transport endpoint so new events appear without polling
   full snapshots
2. wire the dashboard activity panel and task state refresh to that transport
3. align the streaming dashboard behavior with the eventual replacement for
   bounded `foreman watch` polling semantics

## Open risks

- `reviewed_codex.py` and `reviewed_claude.py` are bootstrap supervisors, not
  the Foreman product itself; their behavior should not accidentally become the
  long-term architecture.
- The bootstrap CLI still requires explicit `--db PATH` selection for
  SQLite-backed lifecycle, inspection, monitoring, and human-gate commands
  because engine-instance configuration does not exist yet.
- `foreman watch` and the dashboard activity feed still rely on bounded polling
  snapshots rather than a live streaming transport.
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
- The spec describes `foreman watch` as a live event tail, while the current
  implementation intentionally renders bounded polling snapshots until a
  dedicated streaming transport boundary exists.

## Open decisions

- whether the dashboard activity surface should reuse `foreman watch`
  semantics or move to a dedicated streaming channel
- whether project `default_model` should be validated against the selected
  backend instead of being passed through verbatim at runtime
- whether engine-level database discovery should replace the current explicit
  `--db` requirement
- whether the security review flow should be implemented as a separate shipped
  workflow or as a parameterized branch of the default workflow
