# ROADMAP

## Principle

Roadmap items should preserve the product identity defined in the Foreman spec:

- SQLite-backed structured state,
- declarative roles and workflows,
- spec-driven project initialization,
- explicit sprints, tasks, runs, and events,
- reviewable autonomous execution,
- repo-local context projection under `.foreman/`,
- a dashboard aligned with the design in `docs/design/dashboard-v7/`.

Incremental slices must still aim at durable production architecture. Bootstrap
status does not justify implementation shapes that are knowingly meant to be
replaced wholesale.

## The roadmap from 2026-11-19 (owner)

Agreed with the owner on 2026-11-19 after sprint 60. It replaces the
milestones below, which are kept as history, and orders the "Owner
directions" of `docs/sprints/backlog.md`. Each stage gets an ADR before its
code, and before each subsystem's ADR the existing tools are surveyed.

What Foreman is becoming: a software factory. People talk with clients,
write the specs and documentation (fed in from outside later), accept,
supervise and correct; agents build. Work done through Foreman is fully
registered: nothing is developed without being listed. Foreman runs on a
central server shared by the company, with workers on other machines, and
coordinates several harnesses and models.

### Stage 1 — the core, proven (sprint 61, done 2026-11-20)

Outcome numbers per project, role and model; the lease fencing token checked
on writes; the carried engine items; the seven functions over 200 lines; the
CLI's reads through services. Then Assay runs a whole sprint unattended and
what that shows is fixed. Everything later stands on an engine that can be
left alone, and is judged by the numbers.

### Stage 2 — the manager and people

The design agreed on 2026-11-19 is in `docs/sprints/backlog.md` ("Owner
decisions, 2026-11-19"). In order:

1. A simple identity system inside Foreman (owner, 2026-11-19: "We
   shouldn't be blocked by something so simple"). People sign in to Foreman
   itself; a company-wide identity service can replace it later.
2. The manager as project lead: sees everything, investigates freely,
   operates Foreman directly when asked (recorded under the person's name),
   writes no product code. Its vocabulary gains per-task model and policy
   overrides, notes to the developer, the workflow before a task starts,
   and engine control.
3. People in a project: owner and member; a responsible person per task,
   separate from whether the task is accepted; handing over; a change to
   someone else's work is a request to them; a change based on an
   out-of-date task is refused, saying what changed and by whom.
4. Notices to the responsible person and always to owners, with a view of
   pending work.
5. One manager conversation per person per project.
6. The record closed at `main`: only Foreman's merge moves it, and a commit
   on `main` with no task behind it is reported.

### Stage 3 — a method for the agents

A way of working built into Foreman's roles, workflows and generated
`AGENTS.md`: planning before code, tests with the change, commits and
branches, which docs a change updates, what the developer reports and with
what evidence, when to stop and ask, how a reviewer judges. The planner step
per task (criteria and a protected test written by someone other than the
developer) belongs here. Claude writes a proposal for the owner to correct.

### Stage 4 — resources and environments

Project resources (databases, service accounts, secrets, buckets) recorded
with where they live, which task created them, how to remove them, and a
reference to their secret, never its value. Per-run environments through
the test and worktree set-up commands, with a documented pattern. A step
that creates something outside the repository is recorded and gated by
policy when it touches shared systems.

### Stage 5 — navigation: a left bar

Views per project: board and sprints, backlog, resources, docs (spec, ADRs,
status read in place; the spec editor may grow from it), people, activity,
statistics, tests (what must be tested, suites, coverage), settings.
Workspace level: projects, shared roles and workflows, later machines. The
views are designed together as one system before any one is built (owner,
2026-11-23; backlog, owner directions 5 and 6). It revises the approved
design (v7), so a design reference comes first, then one screen at a time.
A view of the code and one of the repository's history are open questions
in that design. The June rule against a code browser no longer holds (owner,
2026-11-23).

### Stage 6 — central server and workers (owner direction 1)

One Foreman on a server, agents run as a service user created at
installation; sign-in through stage 2's identity, replaceable by the
company's; a worker program per machine that connects out, works in its own
clones and sends events and branches back; machines carry labels and steps
state what they need. Alongside: the database out of the repository,
migrations as a deploy step, a deployment guide. First case: the BricsCAD
MCP server on Windows.

### Stage 7 — a fleet of harnesses

Codex made real (smoke test, recorded cost, the same task through both),
then others; harness and model chosen per role, step or task type by
capability or price, judged by stage 1's numbers.

### Stage 8 — above the task (owner directions 3 and 4)

A declarative sprint workflow (plan, tasks, checks on the integrated `main`,
fix tasks into the same sprint until they pass); roles that look at a whole
sprint; releases through existing CI/CD, whose connector also reads CI
checks on task branches.

### Stage 9 — memory

Lessons from reviews and failed attempts fed back into a project's
instructions or retrieved for the task at hand; per-role memory;
company-level knowledge across projects. A first step can come with stage 3:
repeated review findings proposed as additions to the project's
instructions.

### Later, recorded but not scheduled

Shared compute through a cluster manager (owner direction 2); ticketing apps
in both directions; replying from notifications; recurring and
event-triggered loops; projects over several repositories; the spec editor.

### Dependencies

Stage 1 before everything. Stage 2 before 5 and 6. Stage 3 before 7. Stage 4
before 5. Stage 6 before the owner's colleagues use Foreman. Stages 7, 8 and
9 in any order after 6.

## History: milestones 0 to 23

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
- the terminal monitoring CLI first exposed board, history, cost, and an
  initial watch surface directly from SQLite
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

- completed on `feat/watch-live-tail-alignment`
- `foreman watch` now delivers recent persisted activity followed by
  incremental live updates instead of repeated polling snapshots
- project, sprint, and run scopes are now explicit, with project watch
  defaulting to the active sprint when one exists
- the CLI and dashboard now share the same persisted-event cursor model even
  though the dashboard still delivers it over SSE

## Milestone 15: Production hardening reset

Goal: correct repo guidance so bootstrap status cannot be read as permission
for prototype-grade product architecture.

Target deliverables:

- tightened repo instructions and architecture rules
- accepted UI and API boundary ADR for the product dashboard
- a ranked hardening detour covering dashboard replacement and other
  half-implemented or structurally weak surfaces

Status:

- completed on `docs/production-hardening-reset`
- bootstrap language now explicitly applies to repo memory and feature
  coverage, not acceptable code quality
- a dedicated React frontend plus Python API boundary is now the accepted
  dashboard direction

## Milestone 16: Dashboard API extraction

Goal: separate dashboard backend contracts from the embedded Python-served UI.

Target deliverables:

- explicit backend modules for dashboard reads, actions, and streaming
- stable JSON and incremental event contracts
- tests and docs that let a separate frontend consume the dashboard API

Status:

- completed on `refactor/dashboard-api-extraction`
- `foreman/services/` now owns dashboard reads, actions, and
  incremental stream payload assembly
- the dashboard runtime wrapper now delegates backend behavior through that
  service layer instead of assembling responses inline

## Milestone 17: Dashboard backend foundation

Goal: replace the raw stdlib dashboard server with an actual product backend
foundation.

Target deliverables:

- FastAPI app and uvicorn runtime for the dashboard
- preserved current JSON and SSE route behavior on the new backend
- backend tests that hit the ASGI app directly

Status:

- completed on `feat/dashboard-backend-foundation`
- `foreman/api/app.py` now owns FastAPI routing and SSE delivery
- `foreman dashboard` now runs through uvicorn instead of stdlib HTTP server
- the legacy shell is still present, but it now rides on the real backend

## Milestone 18: React dashboard foundation

Goal: replace the embedded dashboard shell with a dedicated React frontend.

Target deliverables:

- frontend app scaffold and build pipeline
- initial React implementation of current dashboard surfaces
- integration with the FastAPI backend and extracted dashboard service layer

Status:

- completed on `feat/react-dashboard-foundation`
- `frontend/` now contains the dedicated React and Vite dashboard app
- `foreman/api/runtime.py` no longer embeds product HTML, CSS, or
  browser logic
- `foreman/api/app.py` now serves the built frontend assets while
  preserving the existing JSON and SSE backend contract
- frontend component tests and bundle-build validation now accompany the
  existing dashboard backend regression suite

## Milestone 19: Product surface hardening

Goal: remove or finish known placeholder and structurally weak product
surfaces.

Target deliverables:

- removal or implementation of stub CLI product commands
- remediation of known mockup and settings gaps
- stronger API, frontend, and end-to-end validation for shipped surfaces

Status:

- completed on `feat/dashboard-settings-and-creation`
- dashboard runtime and service naming are now explicit through
  `foreman/api/runtime.py` and `foreman/services/`
- local dashboard development now has Vite `/api` proxying plus
  `npm --prefix frontend run dev:full` for a combined frontend and backend
  loop
- shipped CLI product commands no longer depend on the generic `handle_stub`
  fallback for project, sprint, task, run, or config flows
- settings panel, sprint creation, and task creation now run end-to-end from
  React components through FastAPI endpoints to SQLite persistence
- 15 integration tests cover settings read/update, sprint creation, and task
  creation through both the service layer and FastAPI transport

## Milestone 20: Migration framework bootstrap

Goal: introduce an explicit schema migration path for future SQLite
evolution.

Target deliverables:

- versioned migration metadata for the store
- an ordered upgrade runner for existing databases and fresh initialization
- tests and docs for migration expectations and operator workflow

Status:

- completed on `feat/store-migration-framework`
- `foreman/store/migrations.py` owns the append-only `MIGRATIONS` list; migration 1
  is the current baseline schema
- `ForemanStore.initialize()` creates a `schema_migrations` tracking table and
  applies any unapplied migrations in version order via `migrate()`
- `ForemanStore.schema_version()` returns the highest applied version
- 17 tests in `tests/test_migrations.py` cover integrity, fresh install,
  idempotency, and incremental upgrade
- `docs/adr/ADR-0005-schema-migration-strategy.md` accepted

## Milestone 21: History lifecycle expansion

Goal: extend retention and cleanup beyond `events` after migration support
exists.

Target deliverables:

- lifecycle policy for `runs`, stored prompts, and related history
- retention-safe migrations for expanded cleanup behavior
- docs for operator-facing history lifecycle expectations

Status:

- completed on `feat/history-lifecycle-expansion`
- migration 2 adds `idx_runs_project_completed`; `test_partial_db_upgraded_to_latest`
  now passes
- `ForemanStore.prune_old_runs()` hard-deletes terminal runs and cascades to
  their events; protects runs on blocked/in-progress tasks
- `ForemanStore.strip_old_run_prompts()` nulls prompt text on old terminal
  runs while preserving run records and telemetry
- orchestrator `prune_old_history()` reads `run_retention_days` and
  `prompt_retention_days` from project settings alongside `event_retention_days`

## Milestone 22: Autonomous task selection

Goal: implement `task_selection_mode="autonomous"` in the orchestrator so the
engine can create and execute tasks without human task assignment.

Target deliverables:

- `_select_next_task_autonomous()` in `ForemanOrchestrator`
- placeholder task creation persisted to SQLite with `created_by="orchestrator"`
- per-sprint `max_autonomous_tasks` safety bound (default 5, configurable)
- agent populates task via existing `signal.task_started` handler
- 8 new regression tests in `AutonomousTaskSelectionTests`

Status:

- completed on `feat/autonomous-task-selection`
- `select_next_task()` now dispatches to `_select_next_task_autonomous()` for
  autonomous projects; resumes in-progress tasks first, then creates placeholder
  tasks up to the per-sprint limit

## Milestone 23: `foreman db` CLI surface

Goal: expose schema version inspection and explicit migration application
through the CLI so operators can manage database schema without calling Python
directly.

Target deliverables:

- `foreman db version` — report current schema version; warn when
  `schema_migrations` table is absent
- `foreman db migrate` — apply pending migrations, report each by version and
  description; confirm when already up to date
- `ForemanStore.initialize()` returns `list[int]` of applied versions
- 7 new tests in `DbCommandTests`

Status:

- completed on `feat/db-migrate-cli`
- `foreman db version` and `foreman db migrate` are now shipped CLI surfaces
- the `--db` discovery chain applies to both, consistent with all other
  database-backed commands

## Near-term priorities

- See "The roadmap from 2026-11-19" at the top of this file.
