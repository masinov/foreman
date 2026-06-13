# Foreman Usage Manual

A complete operator's guide to running Foreman — the autonomous development
engine for spec-driven software delivery.

This manual is the detailed reference. For product intent and architecture see
`docs/specs/engine-design-v3.md` (system behavior) and
`docs/mockups/foreman-mockup-v6.html` (UI). For contributor rules see
`AGENTS.md`.

> Convention used throughout: run every Python entry point through the repo
> virtualenv — `./venv/bin/foreman ...`, `./venv/bin/python ...`. Never use a
> system `python`/`pip`.

---

## Table of contents

1. [Mental model](#1-mental-model)
2. [Installation & environment](#2-installation--environment)
3. [Quickstart](#3-quickstart)
4. [Core architecture](#4-core-architecture)
5. [Data model](#5-data-model)
6. [CLI reference](#6-cli-reference)
7. [Roles](#7-roles)
8. [Workflows](#8-workflows)
9. [The multi-model fleet](#9-the-multi-model-fleet)
10. [Completion evidence & the proof gate](#10-completion-evidence--the-proof-gate)
11. [Tiered review](#11-tiered-review)
12. [The meta-agent (manager) & supervision](#12-the-meta-agent-manager--supervision)
13. [Autonomy & task selection](#13-autonomy--task-selection)
14. [Human gates, approvals & merge waivers](#14-human-gates-approvals--merge-waivers)
15. [Cost & time gates](#15-cost--time-gates)
16. [Project settings reference](#16-project-settings-reference)
17. [The dashboard & HTTP API](#17-the-dashboard--http-api)
18. [Monitoring & history](#18-monitoring--history)
19. [Event taxonomy](#19-event-taxonomy)
20. [Database & migrations](#20-database--migrations)
21. [Validation](#21-validation)
22. [Troubleshooting](#22-troubleshooting)

---

## 1. Mental model

Foreman turns a written spec into reviewed, merged code by driving cheap and
frontier LLM "agents" through a declarative workflow, one task at a time.

The hierarchy:

```
Project   one repository + spec + workflow + autonomy level
 └─ Sprint        an ordered batch of work
     └─ Task          one unit of change (a branch, acceptance criteria)
         └─ Run           one agent/builtin invocation at one workflow step
             └─ Event         the append-only audit trail (prompts, outcomes, gates)
```

Two hard commitments shape everything:

- **SQLite is the source of truth.** Projects, sprints, tasks, runs, and events
  all live in a `.foreman.db` next to the repo. Markdown docs are projection,
  not primary state.
- **`.foreman/` is runtime projection, not committed state.** The orchestrator
  writes context files there for agents to read; it is gitignored and
  disposable.

Roles and workflows are **declarative TOML** (`roles/*.toml`,
`workflows/*.toml`), not hard-coded. Both **Claude Code and Codex** are
first-class agent backends.

---

## 2. Installation & environment

Foreman expects a virtualenv at `./venv`.

```bash
python3 -m venv venv
./venv/bin/pip install -e . --no-build-isolation
./venv/bin/foreman --version
```

Backend prerequisites (validated by preflight before any long run):

- **Claude Code backend:** a `claude` executable on `PATH`.
- **Codex backend:** a `codex` executable on `PATH` plus a working app-server
  initialize + thread-start handshake.

Preflight failures stop *before* `agent.started`, produce exactly one failed
run, and consume no infrastructure retries — so a missing backend never burns
the retry budget.

---

## 3. Quickstart

```bash
# 1. Initialize a repo as a Foreman project (creates <repo>/.foreman.db).
./venv/bin/foreman init /path/to/repo \
    --name "My Project" \
    --spec docs/spec.md \
    --workflow development

# 2. Plan a sprint.
./venv/bin/foreman sprint add <project-id> \
    --title "Auth slice" --goal "Ship token auth"

# 3. Activate it.
./venv/bin/foreman sprint activate <sprint-id>

# 4. Promote a task into the sprint.
./venv/bin/foreman task add <project-id> \
    --title "Add JWT issuance" \
    --type feature \
    --criteria "issue_token() returns a signed JWT; tests pass" \
    --sprint <sprint-id>

# 5. Run the engine against the project (sequential task execution).
./venv/bin/foreman run <project-id>

# 6. Watch it work.
./venv/bin/foreman watch <project-id>
```

`foreman run <project-id>` advances the active sprint task-by-task through the
project's workflow until it finishes, blocks, or hits a human gate. Use
`foreman run <project-id> --task <task-id>` to drive a single task.

Most commands accept `--db PATH`; by default they discover the repo-local
`.foreman.db`.

---

## 4. Core architecture

Four subsystems (preserved from the spec — do not collapse them):

| Subsystem | Module | Responsibility |
|---|---|---|
| **Agent Runner** | `foreman/runner/` | Launch a native `claude`/`codex` process, normalize its stream into `AgentEvent`s, retry on infrastructure errors. |
| **Role System** | `foreman/roles.py`, `roles/*.toml` | Declarative agent identity: backend, model(s), tools, prompt template, env. |
| **Workflow Engine** | `foreman/workflows.py`, `workflows/*.toml` | The state machine: steps, outcomes, transitions, gates, fallback. |
| **Orchestrator** | `foreman/orchestrator.py` | Ties it together: selects tasks, builds prompts, runs steps, resolves transitions, enforces gates, persists everything. |

A single step executes like this:

1. Orchestrator picks the next runnable task and the current workflow step.
2. It resolves the **model** for the step (overrides → ladder → role → project
   default), emitting `workflow.model_selected`.
3. It builds the **prompt** from the role template + task context (+ completion
   evidence/diff for decision roles).
4. The runner streams the agent; events are persisted against the run.
5. The agent's terminal output is normalized to a canonical **outcome**.
6. The workflow engine finds the **transition** for `(step, outcome)` and moves
   on — or blocks/pauses/finishes.

Built-in (non-agent) steps are prefixed `_builtin:` — `_builtin:run_tests`,
`_builtin:merge`, `_builtin:mark_done`, `_builtin:human_gate`.

---

## 5. Data model

All entities live in SQLite (`foreman/store.py` is the only data-access layer).

- **Project** — `id`, `name`, `repo_path`, `spec_path`, `workflow_id`,
  `default_branch`, `autonomy_level` (`directed`/`supervised`/`autonomous`),
  `settings` (JSON).
- **Sprint** — `id`, `project_id`, `title`, `goal`, `status`
  (`planned`/`active`/`completed`), `order_index`, `started_at`/`completed_at`.
- **Task** — `id`, `sprint_id`, `project_id`, `title`, `description`,
  `task_type` (`feature`/`fix`/`refactor`/…), `status`
  (`todo`/`in_progress`/`blocked`/`done`/`cancelled`), `acceptance_criteria`,
  `branch_name`, `depends_on_task_ids`, `complexity` (`small`/`medium`/`large`),
  `executor_overrides` (per-step model pins), plus workflow runtime fields
  (`workflow_current_step`, `workflow_carried_output`, `step_visit_counts`,
  `completion_evidence`).
- **Run** — one invocation: `role_id`, `workflow_step`, `agent_backend`,
  `status`, `outcome`, `outcome_detail`, `model`, `cost_usd`, `token_count`,
  `duration_ms`, `retry_count`, `session_id`.
- **Event** — append-only audit row: `run_id`, `event_type`, `payload` (JSON),
  `timestamp`. See [§19](#19-event-taxonomy).
- **Gate** — a pending human decision attached to a paused task.

---

## 6. CLI reference

Top-level: `init · projects · project · sprint · task · run · status · board ·
watch · cost · history · transcript · approve · deny · waive-merge ·
revoke-waiver · roles · workflows · config · db · dashboard`.

### Project lifecycle

```bash
foreman init <repo_path> --name NAME --spec SPEC \
    [--db DB] [--workflow WORKFLOW] [--default-branch BRANCH] [--test-command CMD]
foreman projects                      # list all tracked projects
foreman project <project-id>          # inspect one project
foreman status                        # cross-project overview
foreman config <project-id> [--set key=value]   # read / mutate settings
```

`--workflow` defaults to `development`; use `development_secure`,
`development_tiered`, or `development_with_architect` as needed.

### Sprints

```bash
foreman sprint add <project-id> --title TITLE --goal GOAL
foreman sprint activate <sprint-id>
foreman sprint list <project-id>
foreman sprint complete <sprint-id>
```

### Tasks

```bash
foreman task add <project-id> --title TITLE --criteria CRITERIA \
    [--type TYPE] [--description DESC] [--sprint SPRINT_ID] \
    [--depends-on id1,id2] [--complexity {small,medium,large}]

foreman task override <task-id> \
    [--step STEP=MODEL ...] [--ladder-start N] [--clear]

foreman task list <project-id>
foreman task show <task-id>           # task + recent runs + events + overrides
foreman task block <task-id>
foreman task unblock <task-id>
foreman task cancel <task-id>
```

`--depends-on` ids are validated to exist in the same project. `task override`
step ids are validated against the project's workflow. Example:

```bash
foreman task override task-123 --step develop=MiniMax-M2 --step review=claude-opus-4-8 --ladder-start 1
```

### Execution

```bash
foreman run <project-id> [--task TASK_ID] [--db DB]
```

### Human gates & waivers

```bash
foreman approve <task-id> [--note NOTE]
foreman deny <task-id> [--note NOTE]
foreman waive-merge <task-id> [...]   # allow a merge despite a weak proof gate
foreman revoke-waiver <task-id>
```

### Monitoring

```bash
foreman board [<project-id>]          # terminal task board
foreman watch <project-id>            # tail active sprint (live)
foreman watch --sprint <sprint-id>    # tail one sprint
foreman watch --run <run-id>          # tail one run
foreman cost <project-id>             # cost / token totals
foreman history <task-id>             # run + event history for a task
foreman transcript <run-id>           # full persisted transcript for one run
```

### Introspection & DB

```bash
foreman roles                         # list shipped roles
foreman workflows                     # list shipped workflows
foreman db version                    # current schema version
foreman db migrate                    # apply pending migrations
foreman dashboard                     # start the web dashboard
```

---

## 7. Roles

A role is a declarative TOML file describing one agent identity. Shipped roles:

| Role | Model (default) | Session | Purpose |
|---|---|---|---|
| `architect` | `claude-opus-4-6` | ephemeral | Plan/decompose into tasks (emits `signal.task_created`). |
| `developer` | project default | persistent | Implement the change on the task branch. |
| `developer_worker` | project default | persistent | Worker-fleet developer; carries a commented `[agent.env]` example. |
| `code_reviewer` | `claude-sonnet-4-6` | ephemeral | Agentic review with repo tools. |
| `security_reviewer` | `claude-sonnet-4-6` | ephemeral | Security-focused review (in `development_secure`). |
| `triage_reviewer` | `claude-haiku-4-5` | ephemeral | Cheap payload-only triage; can `ESCALATE`. |
| `frontier_reviewer` | `claude-opus-4-8` | ephemeral | Tool-less frontier adjudication of a curated diff. |

### Role TOML anatomy

```toml
id = "developer"
name = "Developer"

[agent]
backend = "claude_code"            # or "codex"
model = "claude-sonnet-4-6"        # "" → project default_model
session_persistence = true         # reuse --resume session across runs
permission_mode = "bypassPermissions"
disallowed_tools = []
# Optional escalation ladder (see §9):
model_ladder = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"]

# Optional per-endpoint environment (see §9):
[agent.env]
ANTHROPIC_BASE_URL = "https://api.example.io/anthropic"
ANTHROPIC_AUTH_TOKEN = "env:EXAMPLE_API_KEY"
CLAUDE_CONFIG_DIR = "env:EXAMPLE_CONFIG_DIR?~/.foreman/claude-example"

[completion]
# How the engine interprets this role's terminal output.
[completion.output]
extract_decision = true            # decision role: parse APPROVE/DENY/STEER/ESCALATE

[prompt]
template = """..."""                # supports {task_title}, {acceptance_criteria},
                                    # {completion_evidence}, {completion_diff}, …
```

`extract_decision = true` marks a role as a **decision role**: it receives the
completion-evidence block and the curated `{completion_diff}` payload, and its
output is parsed into a canonical reviewer decision.

---

## 8. Workflows

A workflow is a state machine over steps. Shipped workflows:

| Workflow | Entry | Shape |
|---|---|---|
| `development` | `develop` | develop → review → test → merge → done |
| `development_secure` | `develop` | adds a `security_review` step before test/merge |
| `development_tiered` | `develop` | develop → **triage** → (escalate) **frontier review** → test → merge → done |
| `development_with_architect` | `plan` | architect plans tasks, then the development flow |

### Workflow TOML anatomy

```toml
id = "development"
entry = "develop"

[[steps]]
id = "develop"
role = "developer"

[[steps]]
id = "review"
role = "code_reviewer"

# ... _builtin:run_tests, _builtin:merge, _builtin:mark_done ...

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "review"

[[transitions]]
from = "review"
trigger = "completion:approve"
to = "test"
carry_output = false

[[transitions]]
from = "review"
trigger = "completion:deny"
to = "develop"
carry_output = true          # feed the reviewer's reason back to develop

# Conflict recovery resets the step-visit budget:
[[transitions]]
from = "merge"
trigger = "completion:conflict"
to = "develop"

[fallback]
message = "Unhandled workflow outcome. Requires human review."
```

### Outcomes

Agent/builtin terminal results normalize to a canonical set
(`foreman/outcomes.py`): `success`, `failure`, `error`, `killed`, `paused`,
`conflict`, `done`, plus reviewer decisions `approve`, `deny`, `steer`,
`escalate`. Transitions are keyed `completion:<outcome>`. Unknown agent
outcomes normalize to `error` (deterministic fallback).

### Loop protection

Each step visit increments `step_visit_counts[step]`. Exceeding
`max_step_visits` (default 5) blocks the task with a `workflow.loop_limit`
event and a `loop_limit` supervision trigger. The `completion:conflict`
transition explicitly **resets** the visit budget (emitting
`workflow.step_visit_reset`) so conflict recovery doesn't starve the loop.

---

## 9. The multi-model fleet

Foreman runs cheap models (MiniMax, DeepSeek, GLM, Kimi, or an OpenRouter/LiteLLM
proxy) through the **unchanged Claude Code harness** by pointing a role at an
Anthropic-compatible endpoint. There are no worker pools or parallel worktrees —
execution is sequential.

### Per-role endpoint injection

Add `[agent.env]` to a role. Values resolve at run-config build time (resolved
secrets are **never** persisted):

| Form | Meaning |
|---|---|
| `"literal"` | used as-is |
| `"env:NAME"` | host env var `NAME`; missing → preflight failure (one failed run, no retries) |
| `"env:NAME?fallback"` | host env var, else the literal fallback |

Keys ending in `_DIR`/`_PATH` are `expanduser`-expanded. **Use a distinct
`CLAUDE_CONFIG_DIR` per provider** so resumed sessions don't mix endpoint state.

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

### Escalation ladder

Give a role a `model_ladder`. The engine picks the rung by step-visit count, so
repeated failures escalate automatically:

```toml
[agent]
model_ladder = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"]
```

`model` remains the single-model fallback when no ladder is present.

### Per-task overrides

A manager differentiates dispatch per task:

```bash
foreman task add <project> --title ... --criteria ... --complexity large
foreman task override <task-id> --step develop=MiniMax-M2 --step review=claude-opus-4-8 --ladder-start 1
```

**Model resolution precedence** (`resolve_step_model`):

1. Per-task override for the step. If the override model is *in* the role
   ladder, escalation resumes from its index on later visits; otherwise it's
   pinned for every visit (the manager chose it deliberately).
2. Role `model_ladder`, indexed by `ladder_start + (visit − 1)`, where
   `ladder_start` comes from the override, else a complexity map
   (`small/medium`→0, `large`→1), else 0.
3. Role `model`.
4. Project `default_model` setting.
5. `None` (harness default).

Every agent step emits `workflow.model_selected` with `{step, model,
visit_count, source}` where `source` is `override|ladder|role|project_default`.

> Ladder rungs share one role's `[agent.env]`. If different rungs need different
> endpoints, model them as **different roles per step**, not per-model env maps.
> See `docs/adr/ADR-0009` and `ADR-0010`.

---

## 10. Completion evidence & the proof gate

Before a decision role reviews — and before a merge — the engine builds a
**completion evidence** object: changed files, branch diff stat, criteria
checklist, score, verdict, builtin test result, and a `proof_status` of
`pending | passed | failed`. It is built **only for decision roles** and is
invalidated when the task branch head moves (so a second review cycle never sees
stale evidence).

The merge-time **completion guard** (`completion_guard_enabled`, default on)
refuses to merge an implementation task (`feature`/`fix`/`refactor`) when:

- the branch has no material file changes,
- only docs/tests changed for an implementation task, or
- `proof_status != "passed"`.

A blocked guard emits `engine.completion_guard` and raises an
`engine.attention_needed` supervision turn tagged `evidence_failed` (when the
proof gate failed) or `task_blocked`. A human can override criteria-based blocks
with `foreman waive-merge` (but not test-failure or reviewer-denial blocks).

### Criteria judging: heuristic vs LLM

By default each acceptance criterion is judged by a **keyword heuristic**
(zero-config, never makes a network call). You can opt into a cheap-model judge
via a single direct HTTP call to an Anthropic-compatible `/v1/messages`
endpoint:

| Setting | Default | Meaning |
|---|---|---|
| `judge_base_url` / `judge_model` | unset | judge endpoint; unset → heuristic |
| `judge_api_key_env` | unset | host env var holding the judge API key |
| `judge_max_diff_chars` | 24000 | diff cap fed to the judge (head 70% / tail 30%) |

The judge is **strictly opt-in and fail-safe**: any HTTP/timeout/parse error
falls back to the heuristic, so evidence building never crashes the workflow.
`CompletionEvidence.judged_by` records the model (or `heuristic`) and is emitted
in `engine.completion_evidence`.

---

## 11. Tiered review

`development_tiered` spends frontier tokens only on hard cases:

```
develop → triage
triage  --approve--> test
triage  --deny-----> develop (carry reason)
triage  --escalate-> review            (frontier_reviewer)
review  --approve--> test
review  --deny/steer-> develop (carry reason)
test/merge/done identical to development (including completion:conflict)
```

- `triage_reviewer` is a cheap decision role. It reads the evidence block plus a
  curated `{completion_diff}` and returns exactly `APPROVE`, `DENY: <reason>`,
  or `ESCALATE: <why this needs the senior reviewer>`. It is told to escalate
  (never approve) when unsure or when the diff is security-sensitive.
- `frontier_reviewer` is a **tool-less** decision role: it adjudicates purely
  from the curated payload (task + criteria + evidence + `{completion_diff}` +
  developer summary) and returns `APPROVE` / `DENY:` / `STEER:`.

The diff payload is capped by `review_diff_max_chars` (default 16000, head/tail
truncated) and is injected **only** into `extract_decision` roles. The agentic
`code_reviewer` stays available as the tool-enabled escape hatch.

---

## 12. The meta-agent (manager) & supervision

The meta-agent is a durable, store-backed chat session per project — the primary
human↔manager interface, intended to seat a **frontier** model that plans
interactively, promotes plans into tasks, and assigns them to cheaper workers.

### Persistence & state

- Sessions and turns persist in SQLite (`meta_sessions`, `meta_turns`,
  migration 11). History survives dashboard restarts.
- Every turn is prefixed with a freshly regenerated **state header** — a compact
  snapshot of project/workflow/autonomy, sprint list + task counts, the active
  sprint's task table (id, status, type, title, model override, truncated
  blocked reason), pending gates, and the last few noteworthy events. It states
  explicitly: *trust this over your memory of earlier turns.*
- The first turn of a session injects the **operating contract**: the exact
  `foreman` CLI verbs the manager may use (inspect / plan / promote / assign /
  steer) and the hard rules (never edit `.foreman/`, never merge manually, never
  run `foreman run` itself).
- The user turn is persisted *before* the model is invoked; the assistant turn
  is persisted in a `finally` path (flagged `interrupted` on crash) so a turn is
  never silently dropped.
- The manager model is set by the `meta_agent_model` project setting (`--model`;
  empty → harness default).

### Supervision turns (engine → manager)

When the engine needs a decision it raises **one** `engine.attention_needed`
event. Triggers:

| Trigger | Raised when |
|---|---|
| `task_blocked` | a task transitions to blocked (gate, branch violation, signal.blocker, …) |
| `evidence_failed` | a completion/merge guard block where `proof_status` is `failed` |
| `loop_limit` | a task exceeds `max_step_visits` |
| `sprint_resolved` | a sprint finishes and the engine stops (supervised/directed handoff, or no further work) |

The dashboard (or an operator) calls
`POST /api/projects/{id}/meta/supervise` with `{ "event_id": ... }`. The engine
builds a compact **attention digest** (`foreman/digest.py`) and runs one
supervision turn through the persisted session:

- the turn is flagged `origin="supervision"`,
- the consumed `event_id` is recorded; a replayed event is rejected with **409**,
- in **`directed`** projects the digest forbids state-mutating commands and asks
  for a recommendation only; in `supervised`/`autonomous` the manager may act
  per the contract.

Auto-invocation policy (poll-and-call vs. a human button) is a frontend/ops
concern — the backend only provides the endpoint.

---

## 13. Autonomy & task selection

Two related knobs:

- **`Project.autonomy_level`** (`directed` / `supervised` / `autonomous`)
  governs how far the engine advances on its own:
  - `directed` — completes the active sprint and stops; the human starts the
    next.
  - `supervised` — same, but emits `engine.sprint_ready` to surface the next
    queued sprint.
  - `autonomous` — auto-activates the next planned sprint and keeps going until
    work is exhausted.
- **`task_selection_mode`** setting (`directed` / `autonomous`): in
  `autonomous` mode the engine may select and start orchestrator-created tasks,
  which must satisfy the autonomous contract (emit `signal.task_started` with
  title, branch, and acceptance criteria) or they are blocked.

When a sprint resolves and the engine stops (the non-auto-advance paths), it
raises a `sprint_resolved` supervision turn so the manager can decide the next
move.

---

## 14. Human gates, approvals & merge waivers

A workflow may contain `_builtin:human_gate` steps. Reaching one **pauses** the
task (`workflow.paused`) and records a Gate. Resume with:

```bash
foreman approve <task-id> --note "ship it"
foreman deny <task-id> --note "rework error handling"
```

Resume is immediate when a native backend is available, else deferred until the
next run. The dashboard exposes the same via `POST /api/tasks/{id}/approve|deny`
and the gates endpoints.

**Merge waivers** let a human override a *criteria-based* completion-guard block
(missing/incomplete criteria, or docs-only-on-impl-task) — but never a
test-failure or reviewer-denial block:

```bash
foreman waive-merge <task-id>
foreman revoke-waiver <task-id>
```

---

## 15. Cost & time gates

Per-task and per-sprint ceilings stop runaway spend. When a ceiling is hit the
task blocks and a gate event fires:

| Setting | Gate event |
|---|---|
| `cost_limit_per_task_usd` | `gate.cost_exceeded` (scope task) |
| `cost_limit_per_sprint_usd` | `gate.cost_exceeded` (scope sprint) |
| `time_limit_per_task_ms` | `gate.time_exceeded` |
| `runner_max_cost_usd` | aborts a single runner stream (default 1000) |

> Third-party Anthropic-compatible endpoints usually report
> `total_cost_usd = 0` while token counts stay accurate. Foreman tracks
> `zero_cost_token_runs` and surfaces it in project/sprint totals so the UI can
> show "tokens (cost unknown for N runs)". USD precision for those endpoints is
> out of scope — do not rely on dollar gates for zero-cost endpoints.

---

## 16. Project settings reference

Set with `foreman config <project-id> --set key=value` (or the dashboard
settings endpoint). Validated by `foreman/settings.py`.

| Setting | Default | Meaning |
|---|---|---|
| `task_selection_mode` | `directed` | `directed` / `autonomous` task pickup |
| `max_autonomous_tasks` | 5 | cap on autonomously selected tasks |
| `max_step_visits` | 5 | loop-limit per workflow step |
| `test_command` | `""` | command run by `_builtin:run_tests` |
| `time_limit_per_run_minutes` | 0 (off) | per-run wall-clock cap |
| `time_limit_per_task_ms` | 0 (off) | per-task cumulative time cap |
| `cost_limit_per_task_usd` | 0 (off) | per-task cost ceiling |
| `cost_limit_per_sprint_usd` | 0 (off) | per-sprint cost ceiling |
| `runner_max_cost_usd` | 1000 | single-stream cost abort |
| `runner_permission_mode` | `auto` | native runner approval policy |
| `event_retention_days` | 90 | startup event pruning cutoff |
| `context_dir` | `""` | override for `.foreman/` projection dir |
| `completion_guard_enabled` | `true` | enforce the merge proof gate |
| `default_model` | `""` | fallback model when a role pins none |
| `meta_agent_model` | `""` | `--model` for the manager chat session |
| `judge_base_url` / `judge_model` | unset | opt-in criteria judge endpoint |
| `judge_api_key_env` | `""` | host env var for the judge API key |
| `judge_max_diff_chars` | 24000 | diff cap fed to the judge |
| `review_diff_max_chars` | 16000 | diff cap in reviewer prompts |

---

## 17. The dashboard & HTTP API

Start the packaged product surface:

```bash
./venv/bin/foreman dashboard          # serves built React assets via FastAPI
```

For frontend development with Vite HMR against the live backend:

```bash
npm --prefix frontend run dev:full    # backend :8080 + frontend :5173/dashboard
npm --prefix frontend run dev         # frontend only; proxies /api → :8080
```

The backend (`foreman/dashboard_backend.py`) is a thin FastAPI transport over
the `DashboardService` (`foreman/dashboard_service.py`); the service is the only
thing that touches the store. A fresh service is constructed per request, but
the running-agent subprocess registry is **module-level and lock-guarded** so
Run/Stop survives request boundaries.

### Endpoint map

| Method & path | Purpose |
|---|---|
| `GET /api/projects` · `POST /api/projects` | list / create projects |
| `GET /api/projects/{id}` | project payload (incl. `agent_running`, totals) |
| `GET/PATCH /api/projects/{id}/settings` | read / update settings |
| `GET/POST /api/projects/{id}/sprints` | list / create sprints |
| `GET /api/sprints/{id}` · `PATCH` · `DELETE` | sprint detail / edit / delete |
| `GET /api/sprints/{id}/tasks` · `POST` | list / create tasks |
| `GET /api/sprints/{id}/events` | paginated sprint events |
| `GET /api/sprints/{id}/stream` | **SSE** live activity (data_version-gated) |
| `GET /api/tasks/{id}` · `PATCH` · `DELETE` | task detail / edit / delete |
| `POST /api/tasks/{id}/stop\|cancel\|approve\|deny` | task actions |
| `POST /api/tasks/{id}/messages` | post a human message to a task |
| `POST /api/projects/{id}/agent/start\|stop` | start / stop a `foreman run` |
| `POST /api/projects/{id}/meta/message` | one manager chat turn (NDJSON stream) |
| `GET /api/projects/{id}/meta/history` | paginated chat history (`limit`/`before`/`has_more`) |
| `DELETE /api/projects/{id}/meta/session` | clear the manager session |
| `POST /api/projects/{id}/meta/supervise` | run one supervision turn from an attention event |
| `GET/POST /api/projects/{id}/gates` · `PATCH /api/gates/{id}` | human gates |
| `GET /api/roles` · `PATCH /api/roles/{id}` | role inspection / edit |

### Streaming efficiency

The SSE loop and `foreman watch` both gate their expensive query on SQLite's
`PRAGMA data_version`: each 0.25 s tick reads one pragma and only runs the
sprint-events query when another connection has actually committed. Heartbeats
keep the stream alive when idle.

---

## 18. Monitoring & history

- `foreman board [project]` — a terminal task board grouped by status.
- `foreman watch <project|--sprint|--run>` — incremental live tail (shares the
  dashboard's persisted-event cursor model).
- `foreman history <task-id>` — the run + event history for one task.
- `foreman transcript <run-id>` — the full persisted transcript of one run
  (every prompt, message, and outcome).
- `foreman cost <project-id>` — cost and token totals, including the
  zero-cost-token-run count.

History hygiene: when `event_retention_days` is set, the orchestrator prunes old
`events` rows on startup (emitting `engine.event_pruned`), but **preserves**
events for `blocked` and `in_progress` tasks regardless of age.

---

## 19. Event taxonomy

Events are the append-only truth of what happened. Families:

- **`agent.*`** — `prompt`, `message`, `cost_update`, `completed`, `error`,
  `infra_error` (a retried attempt), `killed`. Each `infra_error` increments the
  run's `retry_count`.
- **`workflow.*`** — `step_started`, `step_completed`, `transition`,
  `model_selected`, `paused`, `resumed`, `loop_limit`, `step_visit_reset`,
  `no_transition`, `autonomous_contract_missing`.
- **`engine.*`** — `role_policy`, `completion_evidence`, `completion_guard`,
  `task_created`, `merge`/`merge_blocked`/`merge_conflict`, `branch_violation`,
  `sprint_started`/`sprint_ready`/`sprint_completed`, `attention_needed`,
  `crash_recovery`, `event_pruned`/`run_pruned`, `test_run`/`test_output`.
- **`gate.*`** — `cost_exceeded`, `time_exceeded`.
- **`signal.*`** — agent-emitted signals the engine consumes: `task_started`,
  `task_created`, `blocker`.

---

## 20. Database & migrations

The schema evolves through an **append-only** migration ledger
(`foreman/migrations.py`): a list of `(version, description, sql)` tuples applied
in order and tracked in `schema_migrations`. Never renumber or rewrite a landed
migration.

```bash
foreman db version          # current applied schema version
foreman db migrate          # apply any pending migrations
```

`ForemanStore.initialize()` additionally performs idempotent additive
schema-repair so an older DB gains new columns/tables safely.

Migrations added by the review roadmap:

| # | Contents |
|---|---|
| 11 | `meta_sessions`, `meta_turns` + index (manager persistence) |
| 12 | `tasks.executor_overrides_json`, `tasks.complexity` |

---

## 21. Validation

```bash
# Repo-memory scaffold checks
./venv/bin/python scripts/validate_repo_memory.py

# Full backend suite
./venv/bin/python -m unittest discover -s tests

# CLI surface smoke
./venv/bin/foreman --help && ./venv/bin/foreman roles && ./venv/bin/foreman workflows

# Frontend (only when API payloads changed)
npm --prefix frontend test && npm --prefix frontend run build
```

Work is not "done" if it only compiles, or if it lands a user-facing surface
through an architecture already known to be unacceptable (see `AGENTS.md`).

---

## 22. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| One failed run with `preflight_failed: true` | Backend executable missing or a required `[agent.env]` `env:NAME` var is unset. Install/repair the backend or export the variable; no retries were consumed. |
| Task blocked with `engine.completion_guard` | The merge proof gate failed (weak/docs-only/criteria). Strengthen the change, or `foreman waive-merge` for a criteria-only block. |
| Task blocked at a step with `workflow.loop_limit` | The step bounced `> max_step_visits` times. Inspect `foreman history`; raise `max_step_visits` only if the loop is legitimately long. |
| Manager chat "forgot" recent state | It shouldn't — the state header is regenerated each turn from the DB. If stale, confirm the dashboard is hitting the right `.foreman.db`. |
| `meta/supervise` returns 409 | The `engine.attention_needed` event was already consumed by a prior supervision turn (idempotency guard). |
| Cost shows `$0.00` but tokens are counted | Expected for third-party Anthropic-compatible endpoints; see `zero_cost_token_runs` in totals. |
| Dashboard Run/Stop toggle out of sync | `agent_running` is derived from the module-level process registry; a stale entry clears when the subprocess exits. |
| SSE/watch feels laggy | Both gate on `PRAGMA data_version` at 0.25 s; they only re-query after another connection commits. A same-process writer won't bump it, but those loops never write. |

---

*Generated as part of the review-roadmap closeout. Keep this manual current when
CLI flags, settings, roles, workflows, or API endpoints change.*
