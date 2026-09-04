# Foreman

Foreman is an autonomous development engine for turning a project spec into
reviewable implementation work through structured sprints, tasks, runs, and
human gates.

This repository is still the bootstrap memory for that product. The only
authoritative product inputs are:

- `docs/specs/engine-design-v3.md`
- `docs/mockups/foreman-mockup-v6.html`

Everything else in the repo exists to turn those two artifacts into a working
runtime without losing project memory along the way.

Bootstrap here refers to repo-memory scaffolding and incomplete feature
coverage. It does not mean product code may use throwaway architecture.

## Key references

- **Usage manual (start here for operating Foreman): `docs/MANUAL.md`**
- Agent operating instructions: `AGENTS.md`
- Project status: `docs/STATUS.md`
- Current sprint: `docs/sprints/current.md`
- Backlog: `docs/sprints/backlog.md`
- Architecture baseline: `docs/ARCHITECTURE.md`
- Roadmap: `docs/ROADMAP.md`

`docs/MANUAL.md` is the complete operator's guide — installation, a quickstart,
the full CLI reference, roles/workflows, the multi-model fleet, completion
evidence and the proof gate, tiered review, the meta-agent and supervision
turns, the dashboard HTTP API, settings, the event taxonomy, and
troubleshooting. The sections below are repo-memory and project state.

## Current state

The integrated pre-release baseline now contains:

- the product spec and UI mockup,
- two supervised autonomous entry points in `scripts/`,
- a runnable `foreman/` package with SQLite-backed models, store, and CLI,
- shipped declarative `roles/*.toml` and `workflows/*.toml` plus loader and
  prompt-rendering support,
- an orchestrator with built-ins for tests, merge, mark-done, human gates, and
  runtime context projection into `.foreman/`,
- repo-local `.foreman.db` discovery for normal CLI usage plus optional `--db`
  override semantics,
- `foreman init` defaulting to `<repo>/.foreman.db` for project scaffold
  generation and persisted project initialization,
- persisted human-gate approval and denial flows with deferred or immediate
  native resume depending on runtime availability,
- native Claude Code and Codex runners with structured event capture, retry
  normalization, explicit startup preflight checks, approval-policy handling,
  and persisted session reuse across fresh orchestrator invocations for
  persistent roles,
- optional startup event-retention pruning when `event_retention_days` is
  configured, while preserving history for blocked and in-progress tasks,
- an opt-in `development_secure` workflow that now runs end to end through
  code review, security review, test, and merge with durable carry-output
  semantics,
- store-backed monitoring commands for `board`, `history`, `cost`, and
  live `watch` across project, sprint, and run scopes,
- accepted ADRs for runner session and backend contract boundaries
  (`ADR-0001`), dashboard data access (`ADR-0002`), and the product web UI
  and API boundary (`ADR-0003`), plus the dashboard backend framework
  (`ADR-0004`),
- a dashboard service layer in `foreman/dashboard_service.py` for project,
  sprint, task, action, and streaming payloads,
- a FastAPI dashboard backend in `foreman/dashboard_backend.py` served by
  uvicorn,
- a dedicated React dashboard frontend in `frontend/` with project overview,
  queue-oriented sprint management, task detail, activity feed, human message
  input, decision-gate handling, project switching, a per-project meta-agent
  panel, and live sprint activity updates,
- built dashboard assets in `foreman/dashboard_frontend_dist/` served by the
  FastAPI backend,
- `foreman/dashboard_runtime.py` as the dashboard runtime entrypoint and
  frontend asset guard plus dev-mode launch support,
- unit, integration, and browser-driven E2E coverage across store, CLI,
  orchestrator, runners, dashboard, the React frontend, and runner-backed
  executor seams.

The current repo-memory goal is to keep that baseline coherent while moving
into the next implementation gap rather than leaving finished work stranded on
feature branches.

## Implementation standard

Incremental delivery is expected. Throwaway implementation structure is not.

- production-facing code should land behind boundaries that can survive into
  the finished product,
- the mockup defines UI hierarchy and interaction intent, not permission to
  embed the product UI into backend modules,
- the accepted direction for the dashboard is now a dedicated React frontend
  consuming a Python API and streaming boundary,
- known placeholder or stub product surfaces are treated as debt to remove,
  not as acceptable steady-state architecture.

## Workflow selection

Use the default `development` workflow for standard bootstrap project setup.

Use `development_secure` when a project should require a dedicated security
review after code review. Every shipped workflow runs the test built-in
before any review and ends in a `merge_approval` gate; set the
`merge_approval` setting to `human` when a person must authorize merges.

Example:

```bash
./venv/bin/foreman init /path/to/repo --name "Secure Project" --spec docs/spec.md --workflow development_secure
```

## Native backend preflight

Foreman now validates native backend prerequisites before long-running agent
execution starts.

- Claude Code requires a `claude` executable in `PATH`.
- Codex requires a `codex` executable in `PATH` plus a working app-server
  initialize and thread-start handshake.
- Preflight failures stop before `agent.started`, produce one explicit failed
  run, and do not consume infrastructure retries.

Operator recovery:

1. install or repair the missing backend executable,
2. verify the backend manually from the shell,
3. rerun the blocked task or project once the backend startup path is healthy.

## Multi-model Claude Code endpoints

Foreman can point any Claude Code role at an Anthropic-compatible endpoint by
adding an `[agent.env]` table to the role TOML. This is intended for sequential
worker-model execution through the existing Claude Code harness; it does not
add worker pools, parallel task execution, or multi-worktree behavior.

Environment values support three forms:

- `literal value`
- `env:NAME` for a required host environment variable
- `env:NAME?fallback` for an optional host environment variable

Keys ending in `_DIR` or `_PATH` expand `~`. Use a distinct
`CLAUDE_CONFIG_DIR` per provider so resumed Claude Code sessions do not mix
endpoint state.

MiniMax example:

```toml
[agent]
backend = "claude_code"
model = "minimax-m3"
session_persistence = true
permission_mode = "bypassPermissions"

[agent.env]
ANTHROPIC_BASE_URL = "https://api.minimax.io/anthropic"
ANTHROPIC_AUTH_TOKEN = "env:MINIMAX_API_KEY"
CLAUDE_CONFIG_DIR = "env:FOREMAN_MINIMAX_CONFIG_DIR?~/.foreman/claude-minimax"
```

Manual smoke:

```bash
claude --print --model minimax-m3 'Reply with exactly: minimax-ok'
```

For edit-capable Foreman-style runs, use `permission_mode = "bypassPermissions"`
or an equivalent non-interactive approval setup. A manual smoke on this branch
confirmed MiniMax M3 can use Claude Code `Write` and return `TASK_COMPLETE`
with `--permission-mode bypassPermissions`.

### Escalation ladder and per-task overrides

A role may define `[agent] model_ladder = ["cheap", "mid", "frontier"]`. The
engine selects the rung by workflow step-visit count, so repeated failures
escalate the model automatically; `model` stays the single-model fallback. Each
agent step emits a `workflow.model_selected` event recording the chosen model
and the rule (`override` / `ladder` / `role` / `project_default`).

A manager can differentiate dispatch per task:

```bash
foreman task add <project> --title ... --criteria ... --complexity large
foreman task override <task-id> --step develop=MiniMax-M2 --step review=claude-opus-4-8 --ladder-start 1
```

Different ladder rungs share one role's `[agent.env]`; rungs that need different
endpoints must be modeled as different roles. See ADR-0010.

### LLM-judged completion evidence (opt-in)

By default acceptance criteria are judged by a keyword heuristic. Set these
project settings to use a cheap model instead (any failure falls back to the
heuristic, so it never blocks the workflow):

| Setting | Default | Meaning |
|---|---|---|
| `judge_base_url` / `judge_model` | unset | Anthropic-compatible judge endpoint; unset → heuristic |
| `judge_api_key_env` | unset | host env var holding the judge API key |
| `judge_max_diff_chars` | 24000 | diff cap fed to the judge |
| `review_diff_max_chars` | 16000 | diff cap in reviewer prompts |
| `meta_agent_model` | unset | `--model` for the manager chat session |

`CompletionEvidence.judged_by` records the model (or `heuristic`) and is emitted
in the `engine.completion_evidence` event.

### Tiered review workflow

`development_tiered` inserts a cheap `triage_reviewer` between develop and the
frontier `review`. Triage returns `APPROVE` / `DENY` / `ESCALATE`; only
`ESCALATE` reaches the tool-less `frontier_reviewer`, which adjudicates from a
curated `{completion_diff}` payload. Select it at init with
`--workflow development_tiered`.

### Supervision turns

When a task blocks, hits the loop limit, or its evidence fails, the engine emits
one `engine.attention_needed` event. The dashboard (or an operator) can call
`POST /api/projects/{id}/meta/supervise` with `{ "event_id": ... }` to run one
supervision turn through the persisted manager session; the turn is flagged
`origin="supervision"` and replayed events are rejected with 409. In `directed`
projects the supervise prompt forbids state-mutating commands and asks for a
recommendation only.

## Event retention

Foreman can now prune old `events` rows on orchestrator startup when a
project sets `event_retention_days`.

- pruning is project-scoped and cutoff-based,
- events for `blocked` and `in_progress` tasks are preserved regardless of
  age,
- pruning emits `engine.event_pruned` when rows are removed,
- `runs` rows are not pruned yet, so event retention is only the first layer
  of history cleanup.

## Live watch

`foreman watch` now tails persisted activity incrementally instead of
rendering repeated snapshots.

- `foreman watch <project-id>` tails the active sprint by default and falls
  back to project-wide events when no sprint is active,
- `foreman watch --sprint <sprint-id>` tails one sprint explicitly,
- `foreman watch --run <run-id>` tails one run explicitly,
- the CLI and dashboard now share the same persisted-event cursor model even
  though the dashboard still delivers it over HTTP server-sent events.

## Dashboard direction

The product dashboard now ships through the accepted architecture:

- Python backend modules expose JSON and streaming APIs through
  `foreman/dashboard_service.py` and `foreman/dashboard_backend.py`,
- the dedicated React frontend in `frontend/` owns product UI rendering and
  client state,
- built frontend assets are served by FastAPI from
  `foreman/dashboard_frontend_dist/`,
- mockup alignment remains mandatory for hierarchy and interaction behavior.

The dashboard steers the engine, it does not run it. Per the ADR-0002
amendment, Run, Pause, and a task Stop write `engine_commands` rows that
whichever `foreman serve` holds the project lock consumes; the header reports
that engine's residency, pause state, and heartbeat age. The dashboard holds
no process handles — the one process it may start is a detached
`foreman serve` when nothing is resident on a project yet, because there is
otherwise nobody to send a command to.

Blocked tasks say which kind of blocked they are: `gate` (waiting for a human
decision) or `engine` (the engine's dead letter — a loop limit, a cost or time
gate, a branch violation, a failure, a `stop_task`). Project summaries and
`foreman status` count both.

## Local dashboard development

Use the shipped runtime when you want the packaged product surface:

```bash
./venv/bin/foreman dashboard
```

That binds to `localhost` with no token. To expose the dashboard on a
network, set `FOREMAN_DASHBOARD_TOKEN` (or pass `--token` / `--token-file`)
and bind with `--host`; every `/api` request must then carry the token, and
the manager chat stays loopback-only unless `--allow-remote-manager`. See
the manual's "Access and exposure" section.

Use the dedicated frontend workflow when you want Vite HMR against the live
FastAPI backend:

```bash
npm --prefix frontend run dev:full
```

That command starts the backend on `http://127.0.0.1:8080` and the frontend on
`http://127.0.0.1:5173/dashboard`.

If you only want the frontend dev server, `npm --prefix frontend run dev` now
proxies `/api` requests to `http://127.0.0.1:8080` by default.

## Autonomous entry point

Foreman has two engine entry points, and they are the only ones:

```bash
foreman run <project> [--task TASK_ID] [--json-logs]   # one pass, then exit
foreman serve <project> [--poll-seconds N] [--once]    # resident worker
```

`foreman run` advances the active sprint until nothing is runnable and exits;
the dashboard's Run button spawns the same command. `foreman serve` keeps the
engine resident: when a pass has nothing to do it waits until another process
writes to the database or the poll interval elapses, then runs another pass, so
work queued later is picked up without a person pressing Run. It logs JSON
lines on stderr rather than printing, isolates a failing task by blocking it
with an attention event instead of dying, and exits 0 on SIGTERM.

Both take a per-project **engine lock** (a lease with `resource_type="engine"`),
so only one engine can touch a project at a time; a second one exits non-zero
naming the holder. See
[ADR-0011](docs/adr/ADR-0011-resident-engine-and-project-lock.md) and
[§6.1 of the manual](docs/MANUAL.md#61-foreman-serve-the-resident-engine).

## Steering a resident engine

A resident engine has no terminal, and a signal cannot say "run *that* task".
It is steered through the `engine_commands` table instead — the only control
channel to a running engine, and a durable audit trail of who asked for what:

```bash
foreman engine status <project>                 # holder, heartbeat, state, recent commands
foreman engine pause|resume|shutdown <project>  # [--by WHO], default the OS user name
foreman engine run-task <project> <task-id>     # run this task next
foreman engine stop-task <project> <task-id>    # stop it and block it
```

Each verb queues a row and prints its command id. The engine acknowledges a
command when it picks it up and completes or rejects it with a reason, checking
before every workflow step and on every agent tick — so a `pause` reaches an
agent that has been quiet for twenty minutes. `pause` leaves the task
resumable; `stop_task` blocks it, naming the requester. A `pause`, `stop_task`,
or `shutdown` left pending for an engine that is no longer resident is rejected
at the next startup rather than applied to an engine nobody addressed. See
[§23 of the manual](docs/MANUAL.md#23-talking-to-the-resident-engine).

The bootstrap supervisor scripts that once drove this repository were removed
in sprint 53. Run all Python commands through the repo virtual environment
(`./venv/bin/foreman`).

## Next implementation slice

Phase 0 of the production readiness review
(`docs/reviews/production-readiness-review.md`) shipped as sprint 53: an
unattended run is safe on one machine. Sprint 54 is Phase 1. Slice 1, the
resident `foreman serve` worker and the project engine lock, and slice 2, the
`engine_commands` table and the `foreman engine` CLI, have landed; next is
rewiring the dashboard onto the command table and reporting dead-lettered
tasks, then the intake endpoint, the policy matrix, a per-task planner step,
and worktree isolation.
`docs/sprints/current.md` lists the slice order.

## Validation

Current repo-memory validation:

```bash
./venv/bin/python scripts/validate_repo_memory.py
./venv/bin/python -m py_compile scripts/repo_validation.py
./venv/bin/python -m py_compile scripts/validate_repo_memory.py
```

Current code-level validation also includes:

```bash
./venv/bin/pip install -e . --no-build-isolation
npm --prefix frontend test
npm --prefix frontend run build
./venv/bin/python scripts/dashboard_dev.py --help
./venv/bin/python -m unittest discover -s tests -v
./venv/bin/foreman --help
./venv/bin/foreman projects
./venv/bin/foreman status
./venv/bin/foreman roles
./venv/bin/foreman workflows
./venv/bin/foreman approve --help
./venv/bin/foreman deny --help
./venv/bin/foreman board --help
./venv/bin/foreman history --help
./venv/bin/foreman cost --help
./venv/bin/foreman watch --help
./venv/bin/foreman dashboard --help
./venv/bin/python scripts/dashboard_dev.py --help
```
