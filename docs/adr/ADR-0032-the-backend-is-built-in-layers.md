# ADR-0032: The backend is built in layers, and a test holds them

- **Status:** accepted
- **Date:** 2026-11-19
- **Sprint:** 60 (slice 14)

## Context

The owner read the backend and found it disordered: the root of the
`foreman` package held about forty modules of every kind side by side, nine
of them prefixed `dashboard_`, and some of them thousands of lines long. The
owner asked for the architecture to be fixed.

What was there, measured on `d112f6e`:

- The root mixed every layer. The model and its rules (`models`, `policy`,
  `settings`), the store's migrations, git and worktrees, roles and
  workflows, the engine's entry points (`orchestrator`, `serve`, `builtins`,
  `engine_lock`, `engine_control`) beside `engine/`, the rules for a
  person's changes (`mutations`), the manager (`meta_agent`, `proposals`,
  `planning`, `digest`) and the dashboard's own code.
- `foreman/dashboard/` had been created for the HTTP app and its routers,
  and the move had stopped half-way. `dashboard_service.py` (2,408 lines,
  one class of about a hundred methods) and six other `dashboard_` modules
  stayed at the root. The routers reached them through `...dashboard_task_reads`.
  `dashboard_task_reads` imported from inside the package and from
  `dashboard_service`. `dashboard_backend.py` was an eleven-line leftover
  kept for old import paths. The CLI imported `dashboard_service`.
- The rules for a person's change (`Mutations`) imported the orchestrator,
  and the engine imported `Mutations`. About sixty imports were placed
  inside functions, mostly to get round such cycles.
- A lease was handled in four modules: `leases.py`, `task_lease.py`,
  `store/leases.py` and `engine/leasing.py`.
- Nothing checked any of this. The implementation standard in `AGENTS.md`
  says to keep durable seams, but no test held a seam, so each slice put
  its file next to the last one.

## Decision

**The backend is a stack of layers. A module imports only from its own
layer and the layers below it. An `import-linter` contract states the
stack, and CI fails on an import that breaks it.**

The stack, top to bottom (`.importlinter`):

| Layer | Package | What it is |
|---|---|---|
| entry | `__main__`, `cli/` | commands; a command calls services, or the engine for `foreman run` and `foreman serve` |
| HTTP | `api/` | the FastAPI app, routers, schemas, the browser guard, the runtime that serves it. It turns service errors into the error envelope (ADR-0019) and holds no rules |
| services | `services/` | what a person can read and do, one module per area (projects, sprints, tasks, backlog, intake, proposals, gates, worktrees, definitions, the workspace's reads, access). The CLI and the API call the same functions |
| manager | `manager/` | the project manager agent (ADR-0022): its session, its proposals, planning and the attention digest |
| engine | `engine/` | what runs the work: the orchestrator, the resident engine (`resident`), the project lock, the step loop, built-in steps, agent steps, leases held, gates, evidence |
| changes | `mutations/` | the rules for a change a person or a policy makes, each written with its audit event. The engine uses them when it acts by policy (planning backlog work, filing a follow-up) |
| history | `history/` | the runs and events of the work, written once, and their mirror in the process log. The engine and the rules for a person's change both write through it |
| parts | `definitions/`, `repo/`, `notifications/`, `runner/` | roles and workflows and which steps are gates; git, a worktree per task, the context projection and the scaffold; telling people; agent programs. These four do not import each other |
| store | `store/` | SQLite: the connection, the migrations, a part per aggregate |
| domain | `domain/`, `data/` | the model, its rules and errors, with no I/O; the shipped TOML and templates |

Rules that follow:

- **Nothing lives at the root of `foreman/` but `__init__` and `__main__`.**
  The contract is exhaustive over `foreman`: a new module at the root
  belongs to no layer and fails the check.
- **An exception is named in the contract, with its reason, and the list
  only shrinks.** An ignored import that no longer exists fails the check,
  so a fixed exception cannot stay listed.
- **An import is at the top of its module.** An import inside a function is
  kept only for what genuinely must load late: a heavy optional dependency,
  or the `foreman serve` child process. It is never a way round a cycle. A
  cycle is a layering fault and is fixed as one.
- **A layer's errors are its own.** Services raise service errors. The API
  maps them to HTTP and the CLI maps them to exit codes. A lower layer
  never knows about either.

`import-linter` is an existing tool and is used as it is (owner direction:
integrate before building). It needs Python 3.11 or later, so CI runs it on
the 3.12 job only. The 3.10 job runs only the tests.

## How it was reached

The refactor changed no behaviour and no API. It landed as five short
branches on 2026-11-19, each with the full suite and CI green before the
next one started:

1. `refactor/layers-first-moves`: the contract, `domain/`, `repo/`,
   `definitions/`, the engine's root modules into `engine/`, three lease
   modules where there were four. The rules for which workflow steps are
   human gates move out of `engine_control` into `definitions/gate_steps`.
   One exception is listed: `mutations` imports the orchestrator to record
   a gate decision.
2. `mutations/` as a package, split by area. A gate decision is recorded
   without importing the engine, and the exception goes.
3. `manager/`: `meta_agent`, `proposals`, `planning`, `digest`.
4. `services/` and `api/`: `DashboardService` split by area into
   `services/`, the `dashboard_` modules and `backlog` into `services/`, and
   `dashboard/` with its guard and runtime renamed to `api/`.
   `dashboard_backend` is deleted.
5. `notifications/` split by concern. The remaining in-function imports
   are removed, and this document and `docs/ARCHITECTURE.md` are updated to
   the end state.

Logger names do not change. A logger is named on purpose
(`get_logger("serve")` is `foreman.serve`), not after its module, and log
collectors filter on that name.

## Where things went (slice 1)

| Before | After |
|---|---|
| `errors`, `models`, `policy`, `settings`, `outcomes`, `guidance`, `leases`, `api_tokens` | `domain/` |
| `migrations` | `store/migrations` |
| `git`, `worktrees`, `context`, `scaffold` | `repo/` |
| `roles`, `workflows`, `_toml` | `definitions/` |
| `definitions` | `definitions/layers` |
| `engine_control` (human-gate steps, blocked kinds) | `definitions/gate_steps` |
| `engine_control` (the rest) | `engine/control` |
| `orchestrator`, `builtins`, `judge`, `logs` | `engine/` |
| `serve` | `engine/resident` |
| `engine_lock` | `engine/lock` |
| `task_lease` | merged into `engine/leasing` |
| `model_check` | `runner/model_check` |

## Where things went (slice 2)

| Before | After |
|---|---|
| `mutations` (one class of 1,100 lines) | `mutations/`: `base` (`MutationBase`, `MutationError`, the audit event), `tasks`, `gates`, `backlog`, `sprints`; `Mutations` in `mutations/__init__` composes them, as `ForemanStore` composes the store's parts |
| `engine/records` | `history/records` |
| `engine/logs` | `history/logs` |
| the gate decision in `ForemanOrchestrator.resume_human_gate` | `mutations/gates`: `find_gate_stop`, `record_gate_decision`. The orchestrator calls them; `Mutations.decide_gate` no longer imports the engine |

## Where things went (slice 3)

| Before | After |
|---|---|
| `meta_agent` | `manager/agent` |
| `proposals`, `planning`, `digest` | `manager/` |

## Where things went (slice 4)

| Before | After |
|---|---|
| `dashboard/` | `api/` |
| `dashboard_guard`, `dashboard_runtime` | `api/guard`; `api/runtime` (the bind, the security posture, the server) and `api/assets` (the frontend bundle). `runtime` and `app` imported each other; now `runtime` imports `app` |
| `dashboard_backend` (an import shim) | deleted; its importers use `api/app` |
| `dashboard_service.DashboardService` (2,408 lines, about a hundred methods) | `services/`: `ProjectService`, `EngineService`, `SprintService`, `TaskService`, `BacklogService`, `IntakeService`, `ProposalService`, `DecisionGateService`, `WorktreeService`, `DefinitionService`, `WorkspaceService` over `base.Service`, put together by `services.Services`. A route calls `api.tasks.accept_task(...)` where it called `api.accept_task(...)`. A service that needs another is given it (`BacklogService` and `IntakeService` get `tasks`, `ProjectService` gets `definitions`) |
| `Dashboard*Error` | `services/errors`: `ServiceError`, `NotFoundError`, `InvalidRequestError`, `ActionFailedError`, `UnauthenticatedError`, `ForbiddenError` |
| `dashboard_overview`, `dashboard_task_reads`, `dashboard_workflow_reads`, `dashboard_definitions`, `dashboard_access`, `backlog` | `services/workspace`, `task_reads`, `workflow_reads`, `definition_forms`, `access`, `backlog` |
| `dashboard/task_models` | `services/task_models`: the shape of the task reads, which the services build |

## Where things went (slice 5)

| Before | After |
|---|---|
| `notifications` (one module of 760 lines) | `notifications/`: `policy` (whether to speak), `destinations` (where), `transport` (the payload and the webhook), `delivery` (the queue and the worker) |
| 45 imports inside functions | 3, each a late load of something heavy or platform-specific (`uvicorn`, `httpx`, `ctypes`). The rest are at the top of their module |
| four `if TYPE_CHECKING:` imports "to break a cycle" | real imports: none of them was a cycle once the layers were in place |

Older ADRs name the paths of their day and are left as written. This table
and its successors in later slices translate them.

## What the layers do not settle yet

These are known and not hidden by the contract:

- **The CLI does not call the services.** It calls `foreman.mutations` for
  changes and the store for reads, and a few commands (`foreman project
  set`, `foreman gate`, `foreman notify`, `foreman sprint`, `foreman task`,
  `foreman worktree`) still write rows with the store directly. Each is
  allowed by the stack, which lets a layer reach anything below it. Moving
  each command onto its service is the next slice.
- **Some modules are long, each within one concern:**
  `engine/workflow_runner` (1,175 lines), `engine/resident` (1,091),
  `engine/builtins` (1,048), `cli/tasks` (921), `engine/orchestrator`
  (898). Splitting them needs the same care as `Mutations` (a part per
  concern), and is not a layering fault.
- Import order is sorted (`ruff`'s `I` rule) only in the modules this
  refactor touched. The rule is not on for the whole repository yet.

## Consequences

- A reader finds a module by its layer, and a layer's package says what it
  may use.
- A slice that would put a rule in the wrong layer fails CI instead of
  landing.
- Every import path in the backend changed. Branches open across the
  refactor must be rebased onto it. Running processes must be restarted
  after each merge (the dashboard and any resident engine), because a
  function-level import of a moved module fails in a process that loaded
  the old tree.
