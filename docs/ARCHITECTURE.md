# Architecture

## Status

- Status: integrated pre-release baseline
- Primary source: `docs/specs/engine-design-v3.md`
- UI reference: `docs/design/dashboard-v7/` (ADR-0020)
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

- `foreman/store/` and `foreman/models.py` own persisted state,
- `foreman/roles.py` and `foreman/workflows.py` own declarative configuration,
- `foreman/orchestrator.py` and `foreman/engine/` own workflow execution and
  durable transitions,
- `foreman/worktrees.py` owns the git working trees a task executes in,
- `foreman/runner/` owns backend-specific transport and event normalization,
- `foreman/cli/`, `foreman/dashboard_runtime.py`,
  `foreman/dashboard_service.py`, `foreman/dashboard/`, and
  `frontend/` expose inspection and control surfaces.

### Engine and store layout (sprint 57)

`ForemanOrchestrator` (`foreman/orchestrator.py`) is the entry point: it runs
a project pass, runs one task under a lease, resumes a human gate, and walks a
task through its workflow one step at a time. The step loop reads as its
phases: worktree check, limits, branch refresh, the step itself (human gate,
built-in, or agent), the record of what happened, and the transition.

It composes these parts of `foreman/engine/`, each taking only what it uses:

| Module | What it owns |
|---|---|
| `errors`, `results` | what the engine raises and returns |
| `limits`, `model_selection` | validated settings, ceilings, which model a step runs on |
| `leasing` (`TaskLeases`) | lease tokens and heartbeats for the tasks in hand |
| `records` (`RunRecords`) | the only writer of runs, events and attention turns |
| `task_writes` (`TaskWrites`) | writing a task without overwriting an operator |
| `selection` (`TaskSelector`) | directed and autonomous task selection |
| `recovery` (`Recovery`) | orphaned tasks and stale runs after a crash |
| `task_worktrees` (`TaskWorktrees`) | a worktree per task, reclaimed under a cap |
| `branch_sync` | refreshing a task branch and turning conflicts into guidance |
| `prompts` (`PromptBuilder`) | what an agent is told |
| `workflow_runner` (`WorkflowRunner`) | the step loop: checks, the step, the record, the transition |
| `agent_step` (`AgentStepRunner`) | running a role and reading its event stream |
| `signals` (`SignalHandler`) | persisting agent events and applying signals |
| `output_contract` | completion markers and reviewer decisions |
| `evidence` (`EvidenceBuilder`) | the facts recorded before a merge (ADR-0018) |
| `gates`, `sprints`, `retention` | gate policy, sprint flow, history pruning |

`ForemanStore` (`foreman/store/`) is one SQLite connection with a part per
aggregate (`projects`, `sprints`, `tasks`, `runs`, `events`, `gates`, `meta`,
`leases`, `commands`, `tokens`, `notifications`) over `base` (connection,
`_write`, migrations) and `rows` (row to model). Every write goes through
`_write` or `retried_on_lock`, so a held database lock is waited out.


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
- gitignored `.foreman/`, which now also holds the per-task worktrees

The engine's write surface on the operator's checkout is deliberately
*ref-only*. It reads the checkout (refs, `AGENTS.md`, `git log`, `git diff`)
and writes the context projection under `context_dir`, but it never runs
`checkout`, `merge`, or `reset` there. Everything with a working tree happens
in a Foreman-owned worktree (ADR-0012).

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

- shipped `foreman/data/roles/*.toml` and `foreman/data/workflows/*.toml` defaults,
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

### The engine command table

`engine_commands` (migration 15) is the **only** control channel to a resident
engine. Anything that wants to steer one — the CLI, the dashboard, the intake
API — inserts a row; the engine holding the project lock consumes it. The row
is also the audit trail: who asked, when, and what the engine did about it.

- `foreman/models.py` — the `EngineCommand` dataclass, the command and status
  vocabularies, and `EngineLockView`, a token-free read of the engine lease.
  The view deliberately omits `lease_token`: operator surfaces need to know who
  holds a project, not the secret that would let them release it.
- `foreman/store/commands.py` and `foreman/store/leases.py` —
  `enqueue_engine_command`, `list_engine_commands`,
  `next_pending_engine_command`, `mark_engine_command`, and `get_engine_lock`.
  The insert commits on its own connection, which is what makes an idle
  engine's `PRAGMA data_version` wait notice a command without polling a table.
- `foreman/errors.py` — `EngineCommandInterrupt`, a `BaseException` so the
  orchestrator's defensive `except Exception` fallbacks cannot turn an
  operator's `pause` into a failed agent outcome. It lives in `errors.py`
  because the orchestrator must catch it and `foreman/serve.py` imports the
  orchestrator.
- `foreman/orchestrator.py` — the `command_poll` seam, called before every
  workflow step (immediately after the resume point is persisted, so an
  interrupt always leaves a correct resume point) and on every `agent.tick`
  while a runner streams. `_execute_agent_step_guarded` settles an interrupted
  run as `killed` with `gate_type="command"`, reusing the shutdown path.
  `stop_task()` and `release_task()` are the two task-state seams a command
  needs; `record_engine_event()` anchors `engine.command_applied` /
  `engine.command_rejected` on a system run.
- `foreman/serve.py` — the command state machine: startup rejection of
  commands addressed to an engine that is no longer resident, a drain before
  every pass, the paused state, and settlement of an interrupt once the stack
  has unwound. Policy lives here, next to the loop state it changes, rather
  than in the orchestrator.
- `foreman/cli/` — `foreman engine status|pause|resume|shutdown|run-task|
  stop-task`, which read the lock view and enqueue commands.
- `foreman/engine_control.py` — the read-side derivations every surface needs
  over the lock view and the command log, plus the local `foreman serve`
  bootstrap. It exists so the CLI and the dashboard cannot answer "is an
  engine resident", "is it paused", or "why is this task blocked" differently
  from the same database:
  - `describe_engine()` assembles residency, heartbeat age, lease expiry, the
    paused state (derived from the last applied `pause`/`resume`, because the
    flag itself lives in the serve process's memory), the task with a running
    run, and the recent command log;
  - `resolve_gate_steps()` and `blocked_kind()` classify a blocked task as a
    `gate` (parked at a `_builtin:human_gate` step) or an `engine` dead letter
    (loop limit, unhandled outcome, cost or time gate, branch violation,
    failure isolation, `stop_task`), deriving the answer from the workflow
    definition rather than a new column;
  - `spawn_serve()` starts a detached `foreman serve` writing to
    `.foreman/serve.log`, injected as `ServeSpawner` so callers can substitute
    it.

### The dashboard holds no process handles

The dashboard used to spawn `foreman run` and keep the handle in a
module-level dict, so Stop meant killing a process and blocking every
in-progress task — a dead letter the engine never declared. It now steers the
engine the same way every other surface does (ADR-0002 amendment):

- `GET /api/projects/{id}/agent/status` returns the engine view above,
- Run enqueues `resume` (plus `run_task` for a task-scoped start), Pause
  enqueues `pause`, and a task Stop enqueues `stop_task`,
- `GET /api/projects/{id}/engine/commands` exposes the command log, and
  `POST` to it queues `pause`, `resume` or `shutdown` for a resident engine
  (the project page's Stop is `shutdown`). It refuses with a 400 sentence
  when no engine is resident: a `shutdown` queued for nobody would be the
  first thing the next engine read, and it would exit at once,
- when no engine is resident there is nobody to send `resume` to, so the
  service spawns a detached `foreman serve` through its injected spawner —
  the single-machine bootstrap, and the only place the dashboard starts a
  process at all.

### One worktree per task

`foreman/worktrees.py` is the only module that constructs a working-tree path.
`WorktreeManager` is bound to a project and owns the layout under
`worktree_root` (default `<repo>/.foreman/worktrees`):

- `ensure(task)` — the task's tree, on the task branch, created on the first
  develop visit and reused on every later visit,
- `ensure_integration()` — one shared tree pinned to the default branch, where
  `_builtin:merge` runs its `--no-ff` merge,
- `remove(task)` / `remove_path(path)` — deletion, refusing anything outside
  the worktree root,
- `list()` and `prune_project_worktrees(store, project)` — the operator
  surfaces behind `foreman worktree list|prune` and the dashboard's prune
  control,
- `enforce_worktree_limit(store, project, keep_slug=...)` — the
  `max_live_worktrees` policy.

The split inside the module is deliberate: `WorktreeManager` is filesystem and
git only, while the policy that needs to know what a *task* is
(`prune_project_worktrees`, `enforce_worktree_limit`) lives in store-aware
module functions. Nothing in the manager imports the store.

Two settings shape what a tree contains and how many exist.
`worktree_setup_command` runs once inside each newly created tree to build its
own environment, tracked by a marker in the tree's git admin directory so it
never dirties the tree; without it a tree either borrows the operator's tooling
through `worktree_link_paths` or has none. `max_live_worktrees` caps the number
of task trees, enforced by the orchestrator immediately before it creates one —
clean idle trees are reclaimed oldest-first, and a tree holding uncommitted
work is never taken, so the cap yields rather than destroying unmerged state.

The orchestrator holds one manager per project and resolves a working directory
once per step (`_task_working_dir`), which native runner steps, the built-in
executor, the branch invariants, the refresh-before-develop merge, and the
conflict-recovery merge all consume. `tasks.worktree_path` (migration 16)
persists the path so a restarted engine, the CLI, and the dashboard agree on
where a paused task's work lives.

Lifetime is tied to task state, not to a run: a worktree survives human gates,
quota pauses, review rounds, and engine restarts, and is removed by
`_builtin:mark_done`, by cancel and delete, and by `foreman worktree prune`.

The boundary is enforced at run start: `run_project` calls `preflight()` before
leasing any task, so a repository whose worktree root is not ignored, or whose
git predates `git worktree`, fails with one clear message instead of a
half-executed task. See ADR-0012.

### Intake: the third door into the engine

The CLI and the dashboard both assume a person and a sprint.
`POST /api/projects/{id}/intake` is the door for everything else — an incident
tracker, a chat bot, a CI job (ADR-0013).

- `foreman/api_tokens.py` — the only module that mints or hashes a token
  secret, plus the scope vocabulary. Secrets are `fmn_` + 32 random bytes;
  only their SHA-256 is persisted, so the store, the CLI, and the HTTP layer
  share one definition of what a token is and none of them can leak one.
- `api_tokens` (migration 17) — named, per-project, revocable credentials with
  a scope list and a unique index on `token_hash`. `ForemanStore` gains
  `create_api_token` (the one place a secret is returned), `find_api_token`
  (hash lookup, bumps `last_used_at`, invisible to revoked rows),
  `list_api_tokens`, and `revoke_api_token`.
- `tasks.source_system` / `source_ref` / `source_url` / `reporter`
  (migration 17) — where machine-filed work came from, indexed on
  `(project_id, source_system, source_ref)`, which is the idempotency lookup.
- `DashboardService.authenticate_intake` and `intake_task` — the service owns
  both the auth outcome and the filing. Auth raises `DashboardAuthError` (401)
  or `DashboardPermissionError` (403) so the transport maps status codes
  instead of deciding them.
- `foreman/dashboard/` — the route, and the middleware rule that
  keeps the two credentials apart: the shared dashboard token is refused on
  intake, and a project API token is refused on every other `/api` route
  whether or not a dashboard token is configured.
- `foreman/cli/` — `foreman token create|list|revoke`.

Two shapes are worth preserving. **Intake is idempotent on the caller's own
key** `(project, source.system, source.external_ref)`, because the caller is
what retries; Foreman-generated keys would force callers to store Foreman
state. And **the intake queue is a sprint** (`<project>-intake`, created on
first use): sprints stay the unit of grouping, a continuous queue is a sprint
that never completes, and no consumer — task selection, the board, the digest,
the context projection — needs a code path for a task that belongs to no
sprint.

### Views across projects (sprint 58)

Four reads serve the rebuilt dashboard. All sit under `/api/v1` (and the
`/api` alias), live in `foreman/dashboard/routers/projects.py` and
`sprints.py`, and are built by `foreman/dashboard_overview.py` from the
grouped reads in `foreman/store/overview.py`. Query parameters are typed; a
bad one is a 400 `invalid_request` envelope (ADR-0019). Paged lists take
`limit` (1 to 200, default 50) and `offset` (0 or more) and answer with
`total`, `limit` and `offset`.

- `GET /workspace` returns `{"projects": [...]}`; each has `id`, `name`,
  `repo_path`, `default_branch`, `workflow_id`, `engine` (`state` is
  `running`, `paused` or `not_running`, plus `task_id`, `task_key`,
  `task_title`, `step` of the task in flight), `active_sprint` (`id`,
  `title`, `task_counts` by status, `needs_you`, `spend_usd`, or null),
  `needs_you`, `backlog` (triage and todo tasks in the intake queue sprint),
  and `latest_milestone` (or null). Its query count depends on the number of
  projects, never on sprints or tasks.
- `GET /needs-you` and `GET /projects/{id}/needs-you` return `items`, newest
  first: `kind` (`accept_filed_work`, `approve_plan`, `approve_merge`,
  `unblock`), `project_id`, `project_name`, `sprint_id`, `sprint_title`,
  `task_id`, `task_key`, `task_title`, `since`, and for `approve_merge` an
  `evidence` object (`tests_status`, `tested_sha`, `review_outcome`,
  `reviewed_sha`, `head_sha`, `proof_status`; ADR-0018) or null. A gate whose
  policy is `plan_approval` is `approve_plan`; every other human gate is
  `approve_merge`. `since` is the end of the task's last run (what parked it),
  or its creation for filed work never run. A constant number of queries
  whatever the number of projects or tasks.
- `GET /milestones` and `GET /projects/{id}/milestones` return `milestones`
  filtered by `kind` (repeatable or comma-separated): `sprint_started`,
  `sprint_finished`, `task_merged`, `engine_started`, `engine_paused`,
  `engine_resumed`, `engine_stopped`. Each has `kind`, `at`, project, sprint
  and task fields, and `actor`. No table backs them: they are derived from
  sprint columns, `engine.merge` events, completed `engine_commands` (the
  actor is `requested_by`) and the engine lock's lease history (a stop names
  its actor when a `shutdown` command completed during that lease). The
  standing intake queue's start and finish are not milestones.
- `GET /projects/{id}/sprints` accepts `status` (`active`, `planned`,
  `completed`; repeatable or comma-separated), `q` (case-insensitive part of
  the title, which carries the sprint number, or of the id), `limit` and
  `offset`, and now also returns `total`. `order` is `queue` (the default,
  the order sprints run in) or `recent` (latest finished first, then latest
  started; the project page's finished-sprints list). Without parameters it
  returns every sprint as before.

### Inspection and dashboard surfaces

Foreman now exposes two first-class observation surfaces:

- CLI inspection commands: `board`, `history`, `cost`, and live `watch`
- a dashboard service layer in `foreman/dashboard_service.py`, a FastAPI
  transport layer in `foreman/dashboard/`, a React frontend
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
- FastAPI route delivery in `foreman/dashboard/`,
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

### Frontend layout (ADR-0020)

The frontend is being rebuilt to `docs/design/dashboard-v7/` in sprint 58.
`frontend/src/` is laid out as:

| Path | Holds |
|---|---|
| `app/` | `main.jsx` (entry), `mountApp.jsx`, `router.jsx` (History API router and `Link`), `routes.js` (the route table), `paths.js` (every address), `Shell.jsx` and `Breadcrumb.jsx`, `pages.js` (which routes have a built page) |
| `api/` | `client.js` (the `/api/v1` client; errors are `ApiError` from the ADR-0019 envelope; `queryString`), one module per resource (`projects`, `sprints`, `tasks`, `workspace`, `needsYou`, `milestones`, `engine`), `useResource.js` (`{data, error, loading, reload}`, stale responses ignored), `usePagedList.js` (server paging: first page, `loadMore`, `reload`, stale pages ignored) and `ApiProvider.jsx` |
| `ui/` | primitives: `Button`, `Table`, `Surface`, `StatusDot`, `Tabs`, `SectionHeading`, `Mono`, `Menu`, `Dialog`, `Field`, `Disclosure`, and `format.js` |
| `pages/` | `workspace/` and `project/` (built: Sprints and Activity tabs over one shared head, `ProjectLayout`), `shared/` (Needs you, the milestone table, shared wording), `status/` (the shared "being rebuilt" page and not-found) |
| `styles/` | `tokens.css` (the only place a colour, size, radius or line weight is written), `base.css`, `shell.css`, `ui.css`, and one stylesheet per page area |
| `legacy/` | the pre-v7 application, served at `/dashboard/legacy` until the rebuild's last slice deletes it |
| `testing/` | the fake API used by tests |

The entry (`app/main.jsx`) loads either the rebuilt application or the
legacy one by path, each as its own chunk, so the legacy global stylesheet
never reaches rebuilt pages. Routes without a rebuilt page render one shared
"This page is being rebuilt" page linking into `/dashboard/legacy`.
`styles/rules.test.js` fails if a stylesheet other than `tokens.css` names a
colour or a size, if a component uses an inline style, or if a page or
primitive calls `fetch`.

The workspace page reads `GET /workspace`, `GET /needs-you` and
`GET /milestones`. The project page's head (title row, engine, Needs you,
tabs) reads `GET /workspace` for the project, its engine state and backlog
count, and the project's `needs-you`; the breadcrumb's project switcher reads
`GET /workspace` too. Needs you, finished sprints and the Activity tab page on
the server through `usePagedList`; the sprint queue is one unpaged read of the
active and planned sprints.

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
  `merge_approval` human gate; an `auto` gate policy produces a run row, an
  event, and a `policy:<name>` decision record.
- where a person is required is one policy matrix (`foreman/policy.py`,
  ADR-0014): `triage`, `plan_approval`, `merge_approval`, and `notification`,
  each resolved as task override, then a rule for the task's type
  (`policy_rules`), then the project default. Nothing else resolves a policy —
  the orchestrator's gate decision and intake's arriving status both delegate
  to it — and every task's first step records a `policy.resolved` event naming
  the layer that decided each answer. Settings are validated strictly on write
  and read leniently, so a malformed stored value falls back to a default
  rather than stopping a run.
- notification delivery is a durable outbox boundary
  (`foreman/notifications.py`, ADR-0015): the orchestrator maps
  policy-stamped events to one idempotent row per enabled destination, while a
  worker sends due rows outside task execution. Webhook secrets are
  environment references, retries are bounded and persisted, and an exhausted
  delivery emits `notification.failed` without changing the originating task
  outcome.
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
- In autonomous mode the agent names its task with `signal.task_started`
  (title, criteria, task type). The engine gives the task its branch and
  worktree as in directed mode.
- A missing signal emits `workflow.autonomous_contract_missing` once and the
  workflow continues (spec §6.2, degraded path); with the completion guard
  on, the merge is what stops a task that has no acceptance criteria.
- A reported task type or branch that cannot be accepted is refused with
  `signal.rejected` naming the field; the rest of the signal is applied.

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

**Event payloads**
- Events are emitted by name with a dict payload. A module of typed event
  constructors (`foreman/events.py`) existed and was never adopted by the
  engine; it was removed in sprint 56. A typed catalogue belongs with the
  mutation service planned for Phase 3.

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

The engine is resident, steerable through `engine_commands`, isolated from the
operator's checkout by a worktree per task, and every surface that controls it
goes through that table. What it still cannot do is accept work from anything
other than a person at a keyboard: task creation lives on
`dashboard_service.create_task`, needs a sprint, and has no authentication, no
idempotency, and no record of where the request came from.

Both of those doors are now open. `POST /api/projects/{id}/intake`
(ADR-0013) takes work from another system, authenticated with per-project API
tokens and idempotent on an external reference, into a continuous queue sprint.
The policy matrix (ADR-0014) decides what happens to it: `triage` chooses
whether filed work is runnable on arrival or waits in the `triage` status for a
person, while `plan_approval`, `merge_approval`, and `notification` cover the
rest of the "does a person do this?" surface under one precedence rule.

Webhook delivery now acts on that decision through the durable notification
outbox. Additional transports can implement the same boundary without changing
orchestration or policy resolution. The next planned architectural slice is
the per-task planner and its protected acceptance test.
