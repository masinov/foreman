# STATUS

## Current sprint

- Sprint: `sprint-22-react-dashboard-foundation`
- Status: active
- Goal: replace the legacy Python-served dashboard shell with a dedicated
  React frontend on top of the extracted backend API boundary

## Active branches

- no long-lived feature branch should remain loose after the engine DB
  discovery, security-review, backend-preflight, and retention slices; start
  dashboard hardening work from `main`

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
  `foreman/dashboard_api.py`
- reduced `foreman/dashboard.py` to a thinner HTTP adapter over the extracted
  backend contract while preserving the legacy dashboard shell
- strengthened dashboard regression coverage around API and SSE payload
  contracts to prepare the React handoff

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
    explicit startup preflight checks, approval-policy handling, retry
    normalization, and persisted session reuse across fresh orchestrator
    invocations for persistent roles,
  - orchestrator startup event-retention pruning driven by
    `event_retention_days`, with durable `engine.event_pruned` records and
    protection for blocked and in-progress task history,
  - monitoring CLI surfaces for board, history, cost, and live watch tails
    across project, sprint, and run scopes,
  - accepted ADRs for runner session semantics, dashboard data access, and the
    dedicated product web UI and API boundary,
  - an extracted dashboard backend contract in `foreman/dashboard_api.py`
    covering project, sprint, task, action, and incremental streaming
    payloads,
  - a legacy dashboard shell in `foreman/dashboard.py` that still delivers
    project overview, sprint board, task detail, activity feed, human message
    input, activity filtering, project switching, approve or deny actions,
    and a dedicated sprint event stream, but is now explicitly transitional
    and must be replaced,
  - unit and integration coverage across store, CLI, orchestrator, runners,
    dashboard, scaffold, and executor seams,
  - repo-memory docs that are intended to let a fresh agent continue from the
    next slice without reconstructing prior branch history.
- The temporary markdown sprint and status workflow remains intentional
  bootstrap state. The eventual product should move operational state into
  SQLite as described in the spec.

## Ready next

1. replace the legacy dashboard shell with a dedicated React frontend on top
   of the extracted API and streaming boundary
2. remove or implement remaining stub and placeholder product surfaces once
   the new frontend is in place
3. resume lower-level infrastructure detours with the migration framework
   slice after product-surface hardening

## Open risks

- `reviewed_codex.py` and `reviewed_claude.py` are bootstrap supervisors, not
  the Foreman product itself; their behavior should not accidentally become the
  long-term architecture.
- Repo-local discovery currently depends on an existing `.foreman.db` in the
  current repo lineage or on `foreman init` creating one; cross-repo and
  out-of-repo inspection still requires explicit `--db`.
- the current dashboard still ships through a legacy inline shell in
  `foreman/dashboard.py`; the backend contract is extracted now, but the React
  replacement has not landed yet.
- Native backend preflight now validates executable presence and Codex startup
  handshake assumptions, but it does not yet prove downstream auth or service
  reachability beyond startup.
- The Codex app-server protocol exposes token usage but not USD pricing, so
  Codex runs currently persist `token_count` accurately while `cost_usd`
  remains `0.0`.
- multiple CLI product surfaces still route through `handle_stub`, including
  project, sprint, task, run, and config commands.
- `task_selection_mode=\"autonomous\"` is still not implemented in the
  orchestrator even though the project settings model exposes it.
- Event retention currently prunes only `events`; `runs` rows and stored
  prompts continue to accumulate until a later lifecycle or migration slice.
- The SQLite layer still uses bootstrap DDL without a migration framework.
- project-scoped `foreman watch` resolves the active sprint once at startup;
  if sprint ownership changes mid-tail, operators currently need to restart
  the command to follow the new sprint.
- dashboard validation now covers the extracted backend contract directly, but
  there is still no dedicated frontend test stack or end-to-end browser
  coverage.

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
  direction now rejects that interpretation.
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
- whether retention should later prune `runs`, stored prompts, or other
  history surfaces in addition to `events`
- whether the secure workflow should remain an explicit opt-in at init time or
  be selected automatically from project policy in a later slice
- whether project-scoped watch should eventually auto-rebind if a different
  sprint becomes active during a long-lived tail session
