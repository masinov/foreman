# STATUS

## Current sprint

- Sprint: `sprint-17-native-backend-preflight-checks`
- Status: active
- Goal: fail fast when required Claude Code or Codex native backend
  prerequisites are unavailable or misconfigured

## Active branches

- no long-lived feature branch should remain loose after the engine DB
  discovery and security-review slices; start sprint-17 work from `main`

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
    dashboard, scaffold, and executor seams,
  - repo-memory docs that are intended to let a fresh agent continue from the
    next slice without reconstructing prior branch history.
- The temporary markdown sprint and status workflow remains intentional
  bootstrap state. The eventual product should move operational state into
  SQLite as described in the spec.

## Ready next

1. validate `claude` and `codex` executable availability before native runs
   start
2. surface backend preflight failures as explicit operator-facing errors
   instead of generic runtime crashes
3. document backend startup assumptions and recovery steps for bootstrap
   operators

## Open risks

- `reviewed_codex.py` and `reviewed_claude.py` are bootstrap supervisors, not
  the Foreman product itself; their behavior should not accidentally become the
  long-term architecture.
- Repo-local discovery currently depends on an existing `.foreman.db` in the
  current repo lineage or on `foreman init` creating one; cross-repo and
  out-of-repo inspection still requires explicit `--db`.
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
- The spec's CLI examples omit explicit database selection and do not define a
  bootstrap discovery path. The current runtime defaults to repo-local
  `.foreman.db` discovery for normal flows and keeps `--db PATH` as an
  explicit override until engine-instance configuration exists.
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
- whether the bootstrap repo-local `.foreman.db` location should remain
  long-term or give way to a broader engine-instance configuration model
- whether project `default_model` should be validated against the selected
  backend instead of being passed through verbatim at runtime
- whether the secure workflow should remain an explicit opt-in at init time or
  be selected automatically from project policy in a later slice
