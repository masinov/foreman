# ROADMAP

## Principle

Roadmap items should preserve the product identity defined in the Foreman spec:

- SQLite-backed structured state,
- declarative roles and workflows,
- spec-driven project initialization,
- explicit sprints, tasks, runs, and events,
- reviewable autonomous execution,
- repo-local context projection under `.foreman/`,
- a dashboard aligned with the mockup.

## Milestone 0: Repo reset and bootstrap

Goal: make the transplanted scaffold belong to Foreman.

Deliverables:

- Foreman-specific `AGENTS.md`
- current sprint and backlog docs
- architecture baseline and roadmap reset
- wrapper-script alignment
- repo validation that matches the actual project inputs

Status:

- completed on `chore/foreman-autonomy-bootstrap`

## Milestone 1: Core package and CLI shell

Goal: create the first runnable Python package and CLI entrypoint.

Target deliverables:

- `pyproject.toml`
- `foreman/` package scaffold
- `foreman.cli` entrypoint
- `foreman init`, `foreman projects`, and `foreman status` command stubs
- smoke tests for command wiring

Status:

- completed on `feat/cli-package-bootstrap`

## Milestone 2: Structured store and models

Goal: land the SQLite data model described in the spec.

Target deliverables:

- dataclasses or typed models for projects, sprints, tasks, runs, and events
- SQLite CRUD layer
- migration or bootstrap DDL
- tests for round-trips and query helpers

Status:

- completed on `feat/sqlite-store-baseline`

## Milestone 3: Roles, workflows, and scaffold generation

Goal: make projects configurable through TOML plus generated repo artifacts.

Target deliverables:

- role loader
- workflow loader
- prompt rendering
- scaffold generator for `AGENTS.md`, `docs/adr/`, and `.foreman/`
- `.gitignore` update helpers

Status:

- completed on `feat/init-scaffold-generator`
- role and workflow loading, prompt rendering, scaffold generation, and
  `.gitignore` update helpers are now in place

## Milestone 4: Orchestrator and built-ins

Goal: execute one task through a workflow with durable state transitions.

Target deliverables:

- task selection logic
- step transitions and loop limits
- built-ins for tests, merge, mark-done, and human gates
- context projection into `.foreman/context.md` and `.foreman/status.md`

Status:

- completed on `feat/human-gate-resume`
- directed task selection, workflow transitions, loop limits, built-ins for
  tests, merge, mark-done, human-gate pause, human-gate resume, and runtime
  context projection now exist
- bootstrap CLI approvals can defer agent-backed next steps until the native
  runner milestone lands

## Milestone 5: Claude and Codex runners

Goal: move beyond bootstrap wrappers into native runner support.

Target deliverables:

- agent runner protocol
- Claude Code backend
- Codex backend
- structured event capture
- infrastructure retry handling

Status:

- completed on `feat/codex-runner`
- the shared runner protocol, Claude Code backend, Codex backend, retry
  normalization, and orchestrator integration now exist
- native human-gate resume now proceeds immediately when the next backend and
  repo are available, while still persisting deferred state when they are not

## Milestone 6: Monitoring surfaces

Goal: expose Foreman state through CLI and a web dashboard.

Target deliverables:

- board and watch terminal views
- cost and history queries
- project, sprint, and task detail APIs
- web implementation aligned to `docs/mockups/foreman-mockup-v6.html`

Status:

- completed across `feat/monitoring-cli`, `feat/dashboard-shell`,
  `chore/sprint-11-multi-project-polish`, and
  `feat/dashboard-approve-deny-integration`
- the terminal monitoring CLI now exposes board, history, cost, and bounded
  watch snapshots directly from SQLite
- the dashboard now exposes project overview, sprint board, task detail,
  direct SQLite-backed JSON APIs, human message input, activity filtering,
  project switching, and approve or deny workflow resume actions
- the live transport milestone was deferred to a dedicated follow-up slice so
  the dashboard shell could land first without inventing a separate read model

## Milestone 7: Runner contract ADR baseline

Goal: accept the first explicit runtime contract for native runner sessions,
approval boundaries, and backend telemetry.

Target deliverables:

- accepted ADR for session scope and persistence
- accepted ADR for workflow-versus-runner approval handling
- accepted ADR for backend telemetry and unsupported-backend behavior

Status:

- completed on `docs/runner-session-backend-adr`
- `docs/adr/ADR-0001-runner-session-backend-contract.md` is now the active
  runner contract baseline
- cross-invocation session continuity is now an explicit implementation area
  owned by the next milestone

## Milestone 8: Session continuity

Goal: close the documented session-reuse gap from ADR-0001.

Target deliverables:

- reload last compatible native session from SQLite on fresh orchestrator
  invocations
- preserve role-level session policy across Claude Code and Codex
- add regression coverage for cross-invocation reuse and human-gate resume

Status:

- completed on `feat/persistent-session-reload`
- the store and orchestrator now reload the last compatible persisted
  `session_id` for persistent roles on fresh process starts
- regression coverage now covers Claude Code, Codex, and the negative case for
  non-persistent reviewer sessions

## Milestone 9: Dashboard live transport

Goal: replace polling-only dashboard refresh with an explicit event transport
that can evolve into the product's live activity surface.

Target deliverables:

- dedicated dashboard transport endpoint for incremental events
- UI subscription path that keeps activity and task state current
- documented boundary between dashboard live transport and the current bounded
  `foreman watch` model

Status:

- completed on `feat/dashboard-streaming-transport`
- the dashboard now exposes a dedicated sprint event stream for incremental
  persisted activity delivery
- the dashboard client now subscribes to live sprint activity and refreshes
  board state on incoming events without full-list polling
- the dashboard server now runs on a threaded HTTP boundary so long-lived
  streams do not block action endpoints

## Milestone 10: Engine DB discovery

Goal: remove the bootstrap requirement for explicit `--db` selection in normal
SQLite-backed CLI flows.

Target deliverables:

- a default engine database discovery path for repo-local usage
- CLI wiring that uses discovery by default while preserving `--db` override
  semantics
- documentation and tests for initialization, inspection, monitoring, and
  human-gate resume behavior under discovery

Status:

- completed on `feat/engine-db-discovery`
- normal repo-local CLI flows now discover an existing `.foreman.db` by
  walking up from the current working directory
- `foreman init` now defaults to `<repo>/.foreman.db` while `--db` remains a
  deterministic override
- scaffolded repos now keep the default DB file gitignored

## Milestone 11: Security review workflow runtime

Goal: make the shipped secure workflow variant execute end to end with
orchestrator and CLI coverage.

Target deliverables:

- orchestrator coverage for `development_secure` through `security_review`
- explicit approve and deny outcome tests for the security review step
- docs for when bootstrap project initialization should choose the secure
  workflow variant

Status:

- completed on `feat/security-review-workflow`
- `development_secure` now runs end to end through code review, security
  review, test, and merge in orchestrator coverage
- security-review approval and denial paths are now explicit in tests and
  bootstrap docs

## Milestone 12: Native backend preflight checks

Goal: fail fast when required Claude Code or Codex native backend
prerequisites are unavailable or misconfigured.

Target deliverables:

- explicit preflight validation for required `claude` and `codex`
  executables and backend startup assumptions
- clearer persisted and operator-facing errors for preflight failures
- tests and docs for preflight failures and recovery

Status:

- completed on `feat/native-backend-preflight-checks`
- Claude Code and Codex now validate executable availability before
  long-running execution starts
- malformed Codex startup responses now surface as explicit preflight
  failures instead of retryable runtime crashes
- preflight failures now record one explicit error without consuming
  infrastructure retries

## Milestone 13: Event retention pruning

Goal: bring event retention behavior in line with the spec while preserving
history that still belongs to active work.

Target deliverables:

- store support for deleting old events by project and cutoff
- orchestrator startup pruning when `event_retention_days` is configured
- protection for events attached to blocked or in-progress tasks
- tests and docs for retention behavior and operator expectations

Status:

- completed on `feat/event-retention-pruning`
- the store now prunes old project events by cutoff while preserving blocked
  and in-progress task history
- orchestrator startup now honors `event_retention_days` and emits
  `engine.event_pruned` when rows are removed
- retention currently applies only to `events`; `runs` remain intact

## Milestone 14: Watch live-tail alignment

Goal: align `foreman watch` with the dashboard live transport and the spec's
live-tail intent.

Target deliverables:

- an explicit streaming model for `foreman watch`
- incremental persisted activity delivery in the CLI without bounded polling
- tests and docs that explain the boundary between CLI watch and dashboard
  streaming

Status:

- current sprint is `sprint-19-watch-live-tail-alignment`

## Near-term priorities

1. align `foreman watch` with the dashboard live transport and the spec's
   live-tail intent
2. introduce a migration framework once watch alignment is complete
3. decide whether retention should later extend beyond `events` into broader
   history lifecycle management
