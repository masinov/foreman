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
22. [Stopping and interrupting a run](#22-stopping-and-interrupting-a-run)
23. [Talking to the resident engine](#23-talking-to-the-resident-engine)
24. [Worktrees](#24-worktrees)
25. [Intake API](#25-intake-api)
26. [Troubleshooting](#26-troubleshooting)

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

`foreman serve <project-id>` is the same engine kept resident: instead of
exiting when the queue empties it waits and picks up work added later, from any
process. See [§6.1](#61-foreman-serve-the-resident-engine).

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
  (`triage`/`todo`/`in_progress`/`blocked`/`done`/`cancelled`),
  `acceptance_criteria`,
  `branch_name`, `depends_on_task_ids`, `complexity` (`small`/`medium`/`large`),
  `executor_overrides` (per-step model pins and per-task policy), plus workflow
  runtime fields
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

Top-level: `init · projects · project · sprint · task · run · serve · engine ·
status · board · watch · cost · history · transcript · approve · deny ·
waive-merge · revoke-waiver · worktree · roles · workflows · config · db ·
dashboard`.

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
    [--step STEP=MODEL ...] [--ladder-start N] \
    [--gate POLICY=auto|human] [--triage auto|human] \
    [--notification none|attention|all] [--clear]

foreman task list <project-id>
foreman task show <task-id>           # task + worktree + recent runs + events
foreman task accept <task-id>         # triage → todo
foreman task block <task-id>
foreman task unblock <task-id>
foreman task cancel <task-id>         # also removes the task's worktree
```

`task unblock` refuses a task parked at a human gate (use `foreman approve` or
`foreman deny` for those) and clears the engine's dead letters — see
[Dead-letter kinds](#dead-letter-kinds).

`--depends-on` ids are validated to exist in the same project. Only a `done`
dependency releases the task; if a dependency is **cancelled**, the engine blocks
the dependent task ("Dependency cancelled: …", attention trigger
`dependency_cancelled`) for a person to re-plan, unblock, or cancel it. A task
with a running agent step cannot be cancelled while an engine is resident:
stop it first with `foreman engine stop-task`. `task override`
step ids are validated against the project's workflow, and its policy flags are
validated against the policy matrix (section 14). `task accept` moves work out
of `triage`, the status filed work waits in until a person takes it; `task
cancel` works from `triage` too. Example:

```bash
foreman task override task-123 --step develop=MiniMax-M2 --step review=claude-opus-4-8 --ladder-start 1
foreman task override task-123 --gate merge_approval=human --notification all
foreman task override task-123 --triage ""      # drop just that override
```

### Execution

```bash
foreman run <project-id> [--task TASK_ID] [--json-logs] [--db DB]
foreman serve <project-id> [--poll-seconds N] [--once] [--db DB]
```

### Steering a resident engine

```bash
foreman engine status <project-id> [--limit N]      # who holds it, and recent commands
foreman engine pause <project-id> [--by WHO]        # stop taking new work
foreman engine resume <project-id> [--by WHO]       # start again
foreman engine shutdown <project-id> [--by WHO]     # stop and release the lock
foreman engine run-task <project-id> <task-id>      # run this task next
foreman engine stop-task <project-id> <task-id>     # stop it and block it
```

Each verb queues a row in `engine_commands` and prints the command id; `--by`
defaults to the OS user name. See
[§23 Talking to the resident engine](#23-talking-to-the-resident-engine).

### Human gates & waivers

```bash
foreman approve <task-id> [--note NOTE]
foreman deny <task-id> [--note NOTE]
foreman waive-merge <task-id> [...]   # allow a merge despite a weak proof gate
foreman revoke-waiver <task-id>
```

### Worktrees

```bash
foreman worktree list <project-id>    # the trees Foreman owns, and whose they are
foreman worktree prune <project-id>   # drop trees of done/cancelled tasks + dangling ones
                                      # (only git worktrees of this repo; other
                                      # directories under the root are kept)
```

Every task runs in its own git worktree; see [§24 Worktrees](#24-worktrees).

### API tokens

```bash
foreman token create <project-id> --name NAME   # print the secret once
foreman token create <project-id> --name NAME --scope intake
foreman token list <project-id>                 # id, name, scopes, last use
foreman token revoke <project-id> <token-id>    # stop it authenticating
```

The credential other systems use to file work; see [§25 Intake API](#25-intake-api).

### Monitoring

```bash
foreman board [<project-id>]          # terminal task board
foreman watch <project-id>            # tail active sprint (live)
foreman watch --sprint <sprint-id>    # tail one sprint
foreman watch --run <run-id>          # tail one run
foreman cost <project-id>             # cost / token totals, with the input / output /
                                      # cache-read / cache-write split when runs report it
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

### 6.1 `foreman serve`: the resident engine

```bash
foreman serve <project-id> [--poll-seconds N] [--once] [--db DB]
```

`foreman run` exits the moment no runnable task is left. `foreman serve` keeps
the same engine resident: it runs a pass, and when the pass has nothing to do it
sleeps until either another process writes to the database or `--poll-seconds`
(default 5) elapses, then runs another pass. Work queued by the CLI, by the
dashboard, or by another machine sharing the database is picked up without
anyone pressing Run.

**One engine per project.** Before it touches a task, `serve` takes a lease with
`resource_type="engine"` on the project id, and holds it for the whole session.
`foreman run` takes the same lock. A second `serve` — or a `run` — exits
non-zero with a message naming the holder:

```
Another Foreman engine is already running project 'foreman' (lock holder
5e29e543-…, lease expires 2026-09-04T11:54:36Z). Stop it, or wait for its lease
to expire, before starting another.
```

The lock is renewed every 20 seconds from a timer thread on its own database
connection, so a silent agent never costs the engine its project. It is released
on every exit path: a normal stop, `--once`, SIGTERM/SIGINT, and an unhandled
error. After a `kill -9` the project is free again once the 120-second lease
expires. See [ADR-0011](adr/ADR-0011-resident-engine-and-project-lock.md).

**A failed task does not stop the service.** If running a task raises, that task
is marked `blocked` with the error as its `blocked_reason`, an
`engine.attention_needed` event is raised for the supervision digest, and the
engine continues after a backoff — 5 s, doubling per consecutive failure, capped
at 5 minutes, reset after a clean pass. Errors that are not task-scoped (an
unknown project, an invalid `task_selection_mode`) still end the service.

**Structured logs, no printing.** `serve` writes nothing to stdout. Every
lifecycle event goes to stderr as one JSON object per line, and so does every
event the engine persists, so the process log alone tells the story of a run:

```json
{"ts":"2026-09-04T11:52:36.931Z","level":"INFO","event":"serve.lock_acquired","project_id":"foreman","holder_id":"5e29e543-…","lease_id":"lease-087fc41d0f20"}
{"ts":"2026-09-04T11:52:36.932Z","level":"INFO","event":"serve.pass_completed","project_id":"foreman","blocked_task_ids":[],"executed_task_ids":["task-12"],"stop_reason":"idle"}
{"ts":"2026-09-04T11:52:36.932Z","level":"INFO","event":"serve.idle","project_id":"foreman","stop_reason":"idle"}
```

Lifecycle events: `serve.started`, `serve.lock_acquired`, `serve.lock_busy`,
`serve.pass_completed`, `serve.idle`, `serve.paused`, `serve.quota_exhausted`,
`serve.task_failed`, `serve.task_lease_lost`, `serve.lock_lost`,
`serve.stopping`, `serve.stopped`, `serve.lock_released`, and the command
lifecycle (`serve.command_acknowledged`, `serve.command_completed`,
`serve.command_rejected`, `serve.command_interrupting`). A refused start logs
`serve.lock_busy` (with the holder and the lease expiry) at ERROR before it
exits, so a supervisor reading only the log can tell a refusal from a crash.
`serve.idle` and `serve.paused` are narrated once at INFO and then repeated at
DEBUG, so a service that is idle or paused all day does not fill its own log.
`foreman run` can opt into the same format with `--json-logs`.

Mirrored engine events are levelled by family: `engine.*`, `workflow.*`,
`gate.*`, `signal.*`, and the agent step lifecycle (`agent.started`,
`agent.session`, `agent.message`, `agent.command`, `agent.file_change`,
`agent.completed`, `agent.error`, `agent.infra_error`, `agent.killed`,
`agent.rate_limit`) are **INFO**; the per-token, per-tool-call firehose
(`agent.raw_output`, `agent.prompt`, `agent.tool_use`, `agent.tool_result`,
`agent.cost_update`, `agent.tick`) is **DEBUG**, so a resident engine's own
lifecycle is not buried in agent chatter. Every event is still persisted in
full either way; the mapping lives in `foreman.logs.event_log_level`.

`--once` runs exactly one pass and exits, for cron-style deployment and for
tests. Retention pruning and crash recovery run at startup and after any pass
that executed work — never on an idle wake, so an idle engine does nothing
between wakes but re-read `PRAGMA data_version`.

Exit codes: `0` on a clean stop (including SIGTERM), `1` when the lock is
refused, when it is lost to another engine, or on a project-level error.

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
# How the engine interprets this role's final message.
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

### The output contract

The engine reads the role's contract from the agent's **final message** (the
Claude `result`, the Codex `final_answer`, or the last message otherwise).
A developer must end that message with the completion marker; a marker
mentioned earlier in the transcript does not count. A decision role must
state exactly one verdict there: `APPROVE`, `DENY: <reason>`,
`STEER: <action>`, or `ESCALATE: <why>`, optionally prefixed with
`Decision:` or `Verdict:`. Two different verdicts in one message, or a verdict
the role does not declare, are errors; the engine replays the step once with
a correction that lists the role's own options.

Role files declare the contract:

```toml
[completion]
marker = ""
outcomes = ["approve", "deny", "escalate"]   # what this role may return
review_kind = "code"                          # or "security"; used by evidence

[signals]
allowed = ["progress", "blocker"]             # reviewers may not create tasks
```

`outcomes` defaults to approve/deny/steer for decision roles and
done/blocked/error otherwise. Workflow validation checks every transition
against the declared outcomes, and completion evidence counts the latest
`code` and `security` verdicts by `review_kind`, so a new reviewer role needs
no engine change. Signals a role is not allowed to emit are recorded as
`signal.rejected` and never applied; signals inside code fences or quoted
lines are ignored, and the same signal is applied once per step.

---

## 8. Workflows

A workflow is a state machine over steps. Shipped workflows:

| Workflow | Entry | Shape |
|---|---|---|
| `development` | `develop` | develop → test → review → merge_approval → merge → done |
| `development_secure` | `develop` | develop → test → code_review → security_review → merge_approval → merge → done |
| `development_tiered` | `develop` | develop → test → **triage** → (escalate) **frontier review** → merge_approval → merge → done |
| `development_with_architect` | `plan` | plan → human_approval → develop → test → review → merge_approval → merge → done |

Tests run before any review so reviewers judge with real test results in the
engine evidence, and a failing suite goes straight back to develop. Every
workflow ends in a `merge_approval` gate governed by policy (section 14).

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

[[steps]]
id = "merge_approval"
role = "_builtin:human_gate"
policy = "merge_approval"       # resolved through the policy matrix (section 14)

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "test"

[[transitions]]
from = "test"
trigger = "completion:success"
to = "review"

[[transitions]]
from = "review"
trigger = "completion:approve"
to = "merge_approval"
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

### Branch refresh before a develop pass

A task can wait a long time between develop visits (a human gate, a quota
reset, a review round) while the default branch moves. Before every
`develop` step the engine merges the default branch into the task branch when
the branch is behind and the merge is clean, recording `engine.branch_sync`
with `mode="refresh"` and `commits_behind`, and tells the developer in the
carried feedback. A refresh that conflicts is aborted (the tree stays clean)
and handed to the developer as guidance (`engine.branch_sync_conflict`,
`mode="refresh_conflict"`). An unconcluded merge left in the working tree by
an interrupted pass is never aborted: the developer is told to finish it
(`mode="merge_in_progress"`). Merge-time conflicts still route through the
`completion:conflict` transition described above.

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

## 14. The policy matrix, human gates & merge waivers

### The policy matrix

Autonomy in Foreman is a policy, not a mode. One matrix
(`foreman/policy.py`, ADR-0014) answers every question of the form "does a
person do this?":

| Decision | Values | Default | What it governs |
| --- | --- | --- | --- |
| `triage` | `auto`, `human` | `human` | whether work filed through the intake API (§25) is runnable on arrival, or waits in `triage` for a person |
| `plan_approval` | `auto`, `human` | `human` | the architect workflow's plan gate |
| `merge_approval` | `auto`, `human` | `auto` | the merge gate every shipped workflow ends in |
| `notification` | `none`, `attention`, `all` | `attention` | how much a project wants to be told: nothing, attention turns and human gates, or those plus task completions |

Each decision is resolved from three layers, **most specific first**:

1. **the task's override** — `executor_overrides.policy` (any decision), or the
   older `executor_overrides.gates` (the two gate decisions only),
2. **a task-type rule** — the `policy_rules` setting, shaped
   `{"<task_type>": {"<decision>": "<value>"}}`,
3. **the project default** — the setting named after the decision, else the
   built-in default from the table above.

```bash
# A project that merges docs unattended but wants a person on features:
foreman config <project-id> --set merge_approval=human
foreman config <project-id> --set policy_rules='{"docs": {"merge_approval": "auto"}}'

# One task that must not merge without a person, whatever the project says:
foreman task override <task-id> --gate merge_approval=human
```

`foreman config <project-id>` prints the resolved matrix and its rules.
`policy_rules` is validated on write: an unknown task type, decision, or value
is refused there rather than ignored at run time.

Resolution records **where** each value came from — `task_override`,
`task_type_rule` (plus the type), `project_default`, or `built_in_default`.
Every task's first step writes one `policy.resolved` event carrying all four
decisions with their sources, so the audit trail answers why a person was or
was not asked. `GET /api/projects/{id}/policy` returns the same thing, and
`?task_id=` adds the resolution for one task; the dashboard's task drawer shows
it, and the settings panel edits the defaults and the rules.

The `notification` value is stamped as `notify` on each announceable event and
drives a durable delivery queue. `attention` sends engine attention requests
and human gates; `all` adds task completion; `none` queues nothing.

Configure a webhook destination by project:

```bash
foreman notify add <project> --name ops \
  --url https://hooks.example.test/foreman \
  --secret-env FOREMAN_WEBHOOK_SECRET
foreman notify test <project> ops
foreman notify list <project>
foreman notify deliveries <project> [--status pending|delivered|failed]
foreman notify remove <project> ops
```

`--header 'Name: value'` adds a static request header and may be repeated.
`--secret-env` stores only an environment-variable name; when set, each send
reads the key from that variable and adds an HMAC-SHA256 signature. Every
process that drains deliveries must have the variable in its environment.

The orchestrator only queues rows. `foreman serve` sends a bounded batch
between engine passes and `foreman run` drains once before returning, so
receiver latency cannot hold a task open. Failed attempts use exponential
backoff and remain visible in `foreman notify deliveries`; after the fifth
failure the row stays failed and Foreman emits `notification.failed`.

### Human gates

A workflow may contain `_builtin:human_gate` steps. A gate step may declare a
`policy` (`merge_approval` or `plan_approval`), which the matrix resolves:

- **`auto`** — the engine approves the gate itself, completes the run with
  outcome `approve`, emits `workflow.gate_auto_approved`, and writes a
  `human_gate_decisions` row with `decided_by="policy:<name>"`.
- **`human`** — the task **pauses** (`workflow.paused`) until a person acts.

Gate steps without a policy always pause. For production projects set
`merge_approval=human` (or override it per task with
`foreman task override <id> --gate merge_approval=human`) so a person
authorizes every merge. Resume a paused gate with:

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
| `runner_max_cost_usd` | lowers the per-run ceiling a role sets (`[completion] max_cost_usd`); the lower of the two is passed to Claude Code as `--max-budget-usd`, which stops the run when it is reached |

> Third-party Anthropic-compatible endpoints usually report
> `total_cost_usd = 0` while token counts stay accurate. Foreman tracks
> `zero_cost_token_runs` and surfaces it in project/sprint totals so the UI can
> show "tokens (cost unknown for N runs)". USD precision for those endpoints is
> out of scope — do not rely on dollar gates for zero-cost endpoints.

### Backend quota exhaustion

A usage quota running out mid-step (Claude Code's "You've hit your session
limit · resets …" result after a `rate_limit_event` with a status other than
allowed) is an infrastructure condition, not a task failure. The runner raises
`QuotaExhaustedError` with the reset time the backend reported; the retry
loop surfaces it once without spending infrastructure retries; and the
orchestrator **pauses** the task instead of blocking it:

- the task stays `in_progress` with its resume point persisted
  (`workflow_current_step` and the carried output), exactly as a human gate
  persists it, and its step visit is refunded;
- the run is recorded as `failed` with `failure_type="quota"` and an
  `engine.quota_exhausted` event carrying `retry_after`;
- the task lease is released and the checkout restored, so the next pass
  (this engine or another) resumes the task at the same step.

`foreman run` prints the reset time and exits **75** (`EX_TEMPFAIL`).
`foreman serve` logs `serve.quota_exhausted` and waits for the reset (the
reported time plus a few seconds, clamped to one minute to six hours, or
fifteen minutes when the backend did not say) before running the next pass.

---

## 16. Project settings reference

Set with `foreman config <project-id> --set key=value` (or the dashboard
settings endpoint). Validated by `foreman/settings.py`: an invalid value is
rejected at `--set` time and by the dashboard endpoint, and `foreman run`
refuses to start a project whose stored settings fail validation, naming the
offending value, rather than running on silent defaults.

| Setting | Default | Meaning |
|---|---|---|
| `task_selection_mode` | `directed` | `directed` / `autonomous` task pickup |
| `max_autonomous_tasks` | 5 | cap on autonomously selected tasks |
| `max_step_visits` | 5 | loop-limit per workflow step |
| `test_command` | `""` | command run by `_builtin:run_tests` |
| `test_timeout_seconds` | 1800 | wall-clock cap for `_builtin:run_tests`; the process group is killed on expiry; 0 disables |
| `time_limit_per_run_minutes` | 0 (off) | per-run wall-clock cap |
| `time_limit_per_task_ms` | 0 (off) | per-task cumulative time cap |
| `cost_limit_per_task_usd` | 0 (off) | per-task cost ceiling |
| `cost_limit_per_sprint_usd` | 0 (off) | per-sprint cost ceiling |
| `runner_max_cost_usd` | unset (role ceiling applies) | per-run cost ceiling; can lower a role's, never raise it |
| `runner_permission_mode` | `auto` | native runner approval policy |
| `event_retention_days` | unset (off) | prune events older than N days at engine start |
| `run_retention_days` | unset (off) | prune terminal runs older than N days; gate decisions keep their record with the run link nulled |
| `prompt_retention_days` | unset (off) | null stored prompt text on terminal runs older than N days |
| `max_infra_retries` | 3 | infrastructure retries per agent step |
| `active_run_recovery_timeout_minutes` | 0 (derived) | stale-run ownership window for crash recovery |
| `context_dir` | `""` | override for `.foreman/` projection dir |
| `worktree_root` | `""` | where per-task worktrees live; empty means `<repo>/.foreman/worktrees` (see §24) |
| `worktree_link_paths` | `[]` | repo-relative paths symlinked from the operator's checkout into every new worktree; shares your environment rather than isolating it (see §24) |
| `max_live_worktrees` | `4` | ceiling on live task worktrees; the engine reclaims clean, idle trees oldest-first to stay under it. `0` disables the cap (§24) |
| `worktree_setup_command` | `""` | shell command run once in each new worktree to build that tree's own environment (§24) |
| `worktree_setup_timeout_seconds` | `1800` | wall-clock cap for `worktree_setup_command`; `0` disables the timeout |
| `completion_guard_enabled` | `true` | enforce the merge proof gate |
| `merge_approval` | `auto` | `auto` or `human`: whether the `merge_approval` gate needs a person (§14) |
| `plan_approval` | `human` | `auto` or `human`: whether the architect's plan gate needs a person (§14) |
| `triage` | `human` | `auto` or `human`: whether filed work is runnable on arrival or waits in `triage` (§14) |
| `notification` | `attention` | `none`, `attention`, or `all`: what the project wants to be told about (§14) |
| `policy_rules` | `{}` | per-task-type policy overrides, `{"<task_type>": {"<decision>": "<value>"}}` (§14) |
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
thing that touches the store. A fresh service is constructed per request and
holds no process handles: everything Run and Pause do survives request
boundaries because it lives in SQLite, not in the web process.

### Run, Pause, and the engine header

The header reports the engine, not a subprocess: **resident** (an engine holds
the project's engine lock and is heartbeating it), **paused**, or **not
running**, with the age of the last heartbeat.

| Control | What it does |
|---|---|
| **Run** | Enqueues `resume`. A task-scoped start also enqueues `run_task`. If no engine is resident, a detached `foreman serve` is spawned first (see below) and picks the commands up on its first pass. |
| **Pause** | Enqueues `pause` and returns immediately. The engine terminates its running agent step and settles that run as `killed` with the task **resumable**; no task status changes. |
| **Stop** on a task card | Enqueues `stop_task`. The engine blocks the task if it is the one running, and rejects the command with a reason if it is not. |

The dashboard never kills an engine. If a `foreman serve` must go away
entirely, that is `shutdown` (`foreman engine shutdown <project>`), which
releases the lock and exits 0.

The fallback spawn is for the single-machine case: with nothing resident there
is no engine to send `resume` to, so the service starts
`foreman serve <project> --db <path>` detached, with stdout and stderr appended
to `.foreman/serve.log` in the project's context directory. The requester is
recorded on the queued command either way, so the command log answers "who
started this".

### Dead-letter kinds

`blocked` covers two different situations, and the dashboard, `foreman task
show`, `foreman board`, and `foreman status` all name which one:

| Kind | Means | Cleared by |
|---|---|---|
| `gate` | The task is parked at a `_builtin:human_gate` step, waiting for a decision. | `foreman approve` / `foreman deny`, or Approve/Deny on the card |
| `engine` | The engine's dead letter: loop limit, unhandled outcome, cost or time gate, branch violation, failure isolation, or a `stop_task`. | `foreman task unblock`, after fixing whatever stopped it |

The kind is derived, not stored: the task's persisted `workflow_current_step`
is looked up in the project's workflow, and a step run by
`_builtin:human_gate` is a gate. A persisted step alone is not enough, because
the engine also persists a resume point when it blocks a task after a failure.
Project summaries carry `blocked_gate` and `blocked_engine` counts.

### Access and exposure

The dashboard binds to `localhost` by default and is open on that bind. To
expose it on a network, start it with a shared token:

```bash
export FOREMAN_DASHBOARD_TOKEN="$(openssl rand -hex 24)"
./venv/bin/foreman dashboard --host 0.0.0.0            # token read from the env
./venv/bin/foreman dashboard --host 0.0.0.0 --token-file ~/.foreman/dashboard.token
```

- Every `/api` request must carry the token: `Authorization: Bearer <token>`,
  `X-Foreman-Token: <token>`, or `?token=<token>` on GET requests only (used
  by the event stream, because `EventSource` cannot set headers). Missing or
  wrong tokens get **401**. The React shell asks for the token once and keeps it in the
  browser's local storage.
- A non-loopback bind **without** a token is refused. Pass
  `--allow-insecure-network` only on a network you trust.
- The **manager chat** runs a full-access agent session on the server. It is
  enabled on loopback binds and disabled elsewhere (its routes answer **403**)
  unless you pass `--allow-remote-manager`, in which case every token holder
  can run that agent.
- Cross-origin browser calls are refused with **403**, not only left without
  CORS headers: a request whose `Origin` is not the dashboard's own is
  rejected, and so is a write the browser labels cross-site. The shipped
  frontend is same-origin (served by FastAPI, or proxied by Vite). Pass
  `--allowed-origin <origin>` (repeatable) if another web app must call the
  API from a browser.
- Without a token the API answers only to `localhost`, `127.0.0.1`, `::1`
  and the bind host. A proxy in front of a token-less dashboard must keep
  the `Host` header, or you must configure a token.
- Request bodies must be sent as `Content-Type: application/json`.
- Settings that decide what runs on the host cannot be changed through the
  API or the Settings screen (they answer **403** and are shown read-only):
  `test_command`, `worktree_setup_command`, `worktree_root`,
  `worktree_link_paths`, `context_dir`, `judge_base_url`,
  `judge_api_key_env`. Set them at a terminal with
  `foreman config <project-id> --set <key>=<value>`. A role's `backend` and
  `permission_mode` are likewise changed only in its TOML file. See ADR-0017.
- The intake endpoint (§25) is exempt from these three rules; it
  authenticates its own project API token. See ADR-0016.
- `POST /api/projects` accepts only an existing git repository path; set
  `FOREMAN_DASHBOARD_REPO_ROOTS` (`os.pathsep`-separated) to confine projects
  to specific directories.
- `GET /api/sprints/{id}/events` caps `limit` at 500.

A shared token is not identity: every holder is the same actor. Per-user
login and actor attribution arrive in Phase 1. The one exception is the intake
endpoint (§25), which takes a named per-project API token instead and records
which token filed each task.

### Endpoint map

| Method & path | Purpose |
|---|---|
| `GET /api/projects` · `POST /api/projects` | list / create projects |
| `GET /api/projects/{id}` | project payload (incl. `engine`, `blocked_gate`/`blocked_engine`, totals) |
| `GET/PATCH /api/projects/{id}/settings` | read / update settings |
| `GET /api/projects/{id}/policy` | the policy matrix: defaults, rules, and (with `?task_id=`) the resolution for one task (§14) |
| `GET/POST /api/projects/{id}/sprints` | list / create sprints |
| `GET /api/sprints/{id}` · `PATCH` · `DELETE` | sprint detail / edit / delete |
| `GET /api/sprints/{id}/tasks` · `POST` | list / create tasks |
| `GET /api/sprints/{id}/events` | paginated sprint events |
| `GET /api/sprints/{id}/stream` | **SSE** live activity (data_version-gated) |
| `GET /api/tasks/{id}` · `PATCH` · `DELETE` | task detail / edit / delete |
| `POST /api/tasks/{id}/stop\|cancel\|approve\|deny\|accept` | task actions; `accept` moves a `triage` task to `todo` (§14) |
| `POST /api/tasks/{id}/messages` | post a human message to a task |
| `POST /api/projects/{id}/intake` | **file work from another system** (project API token, not the dashboard token — §25) |
| `GET /api/projects/{id}/agent/status` | engine residency, pause state, heartbeat age, current task, recent commands |
| `POST /api/projects/{id}/agent/start\|stop` | queue `resume` (spawning `foreman serve` if none is resident) / queue `pause` |
| `GET /api/projects/{id}/engine/commands` | recent engine commands (`limit`, `status`) |
| `GET /api/projects/{id}/worktrees` | the trees Foreman owns, the root, and `max_live_worktrees` |
| `POST /api/projects/{id}/worktrees/prune` | remove done, cancelled, and unclaimed trees (§24) |
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

- **`agent.*`** — `prompt`, `session` (the backend's session id, model,
  permission mode, and tool count), `message`, `command`, `file_change`,
  `tool_use`, `tool_result` (a capped preview with `is_error` and the full
  length), `raw_output` (every content line of the backend stream, capped at
  8,000 characters with `truncated` and `length` when cut), `cost_update`,
  `rate_limit` (only when the backend reports a status other than allowed),
  `completed`, `error`, `infra_error` (a retried attempt), `killed`. Each
  `infra_error` increments the run's `retry_count`. Progress-only lines from
  the backend (thinking-token counters, allowed rate-limit notices) become
  `agent.tick` heartbeats and are never persisted.
- **`workflow.*`** — `step_started`, `step_completed`, `transition`,
  `model_selected`, `paused`, `resumed`, `loop_limit`, `step_visit_reset`,
  `no_transition`, `autonomous_contract_missing`.
- **`engine.*`** — `role_policy`, `completion_evidence`, `completion_guard`,
  `task_created`, `merge`/`merge_blocked`/`merge_conflict`, `branch_violation`,
  `quota_exhausted` (the backend's usage window ran out; the task is paused
  at its step with `retry_after`),
  `sprint_started`/`sprint_ready`/`sprint_completed`, `attention_needed`,
  `crash_recovery`, `event_pruned`/`run_pruned`, `test_run`/`test_output`,
  `command_applied`/`command_rejected` (one per engine command, carrying
  `command_id`, `command`, `requested_by`, `task_id`, and `detail`).
- **`intake.*`** — `task_created`, one per task filed through the intake API
  (§25), on a synthetic `intake` run. Carries the `source` object, the task
  key, the sprint it landed in, and the filing token's `token_id` and
  `token_name` — never the secret.
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

Each migration is applied atomically: its statements and its ledger row run
inside one `BEGIN IMMEDIATE` transaction, so a failing migration leaves the
database at the previous version and raises `MigrationError`. Two processes
that initialize the same database at once cannot double-apply a version.
`ForemanStore.initialize()` additionally performs a narrow additive
schema-repair for long-lived local databases; it is scheduled for removal.

File-backed databases open in WAL mode with `synchronous=NORMAL` and a 30 s
busy timeout so the engine, the dashboard, and the CLI can share one file.
Expect `.foreman.db-wal` and `.foreman.db-shm` sidecar files next to the
database; scaffolded repositories ignore them. WAL needs a local filesystem.

Recent migrations:

| # | Contents |
|---|---|
| 11 | `meta_sessions`, `meta_turns` + index (manager persistence) |
| 12 | `tasks.executor_overrides_json`, `tasks.complexity` |
| 13 | `projects.task_key_prefix`, `tasks.task_key` (Jira-style keys) |
| 14 | gate tables rebuilt with `ON DELETE` rules, `events(task_id, timestamp)` index, `projects.task_key_seq` + unique task keys |
| 15 | `engine_commands` + `(project_id, status, requested_at)` index (the control channel to a resident engine) |
| 16 | `tasks.worktree_path` (the Foreman-owned checkout a task runs in) |
| 17 | `api_tokens` + unique `token_hash` index; `tasks.source_system`/`source_ref`/`source_url`/`reporter` + `(project_id, source_system, source_ref)` index (intake, §25) |

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

## 22. Stopping and interrupting a run

`foreman run` and `foreman serve` both install SIGTERM and SIGINT handlers.
Stopping the engine (Ctrl+C, `kill <pid>`, or the dashboard's Stop) terminates
every child process group Foreman started (the agent and anything it spawned, or
the test command), records the active run as `killed` with an `agent.killed`
event (`gate_type="shutdown"`), releases the task lease, and leaves the task
`in_progress` at its persisted workflow step so the next run resumes it.

Stopping does **not** touch your checkout — the engine never had it checked out
in the first place (§24). The task's worktree is left exactly as the agent left
it, half-finished edits and all, which is what makes resuming at the same step
meaningful.

The two commands differ only in exit code. `foreman run` exits **130**: the
one-shot run it was asked to complete did not complete. `foreman serve` exits
**0** and logs `serve.stopping` then `serve.stopped`: stopping a resident
service is a requested state change, not a failure, and a supervisor
(systemd, a container runtime) must not treat it as a crash loop. `serve` also
releases the project engine lock on its way out, so a replacement engine can
start immediately.

While an agent is silent, the runner wakes every 15 seconds to enforce the
time and cost gates and to heartbeat the task lease. If another engine has
taken the lease meanwhile, the run is recorded as `killed`
(`gate_type="lease_lost"`) and this engine exits without touching the task.

A third exit code, **75**, means `foreman run` stopped because the agent
backend's usage quota ran out; the task is paused at its step, not blocked
(see §15, "Backend quota exhaustion"). `foreman serve` does not exit in that
case: it waits for the reset and resumes.

---

## 23. Talking to the resident engine

A `foreman serve` process has no terminal. Signals are the only thing an
operating system offers, and a signal cannot say "run *that* task", cannot be
queued for an engine that is not up yet, and leaves no record of who sent it.

So a resident engine is steered through a table. `engine_commands` is the
**only** control channel: the CLI, the dashboard, and the intake API all write
rows to it, and whichever engine holds the project lock consumes them. The row
is the audit trail — it records who asked, when, and what the engine did about
it.

### The commands

| Command | Effect |
|---|---|
| `pause` | Stop picking up new work. A running agent step is terminated and its run settled as `killed`, with the task left **resumable** at its persisted step. The engine stays resident and keeps heartbeating its lock. |
| `resume` | Leave the paused state and run a pass. |
| `run_task <task-id>` | Run that task next, regardless of sprint order. |
| `stop_task <task-id>` | If that task is the one running, terminate its agent step and mark the task `blocked` with `blocked_reason` "Stopped by \<requester\>". |
| `shutdown` | Finish as `pause` does, release the engine lock, exit 0. |

A paused engine changes no task status — pausing is about the engine, not about
the work. A stopped task becomes `blocked`; there is no separate "stopped"
status, because `blocked` already means exactly what a stopped task needs it to
mean: not runnable until a human or the manager says otherwise.

### Lifecycle

Every command moves `pending` → `acknowledged` (the engine has picked it up) →
`completed` or `rejected`, always with a `result_detail` explaining the
outcome, and always leaving an `engine.command_applied` or
`engine.command_rejected` event behind — on a system run for the task involved,
or on a project-level run when no task is involved.

Rejections are ordinary, not errors. A `run_task` naming a task that is
`blocked`, `done`, or owned by another project is rejected with the reason. A
`stop_task` naming a task the engine is not running is rejected rather than
guessed at.

### When no engine is resident

A command that describes *work* outlives the process, so a pending `resume` or
`run_task` is honoured by the next engine to start. A command that describes a
*process* does not: a starting engine rejects every pending `pause`,
`stop_task`, and `shutdown` with `result_detail = "no engine was resident"`,
rather than pausing a service nobody asked to pause. `foreman engine` tells you
which of the two will happen when it queues the command.

### How fast a command lands

An idle engine wakes on `PRAGMA data_version`, and the insert commits from a
different connection, so a queued command wakes the engine within one tick
(0.5 s) rather than waiting out the poll interval. An engine that is mid-task
checks for commands before every workflow step and on every `agent.tick` while
a runner streams, so a `pause` reaches an agent that has been working quietly
for twenty minutes.

An engine that is *deliberately* waiting — backing off after a failed task, or
sitting out a backend quota reset that can be six hours away — also cuts that
wait short when a command arrives. An engine that ignored `shutdown` until the
quota reset would not be controllable, so the wait re-reads `data_version` each
tick and only looks in `engine_commands` when another connection has actually
committed.

### Worked example

```console
$ foreman engine status foreman
Engine status
Database: /src/foreman/.foreman.db
Project: foreman | Foreman
Resident engine: 5e29e543-0e1c-4a6f-9a9e-1c2f1b6d40aa
State: running
Heartbeat: 6s ago (at 2026-09-04T12:31:02.114Z)
Acquired: 2026-09-04T12:14:31.882Z | Lease expires: 2026-09-04T12:33:02.114Z
Current task: task-49 | Add the engine command table
Recent commands (0):
- none

$ foreman engine stop-task foreman task-49 --by carla
Queued engine command: stop_task
Database: /src/foreman/.foreman.db
Project: foreman | Foreman
Command id: cmd-9f1c2a7b41e0
Requested by: carla
Task: task-49
Resident engine: 5e29e543-0e1c-4a6f-9a9e-1c2f1b6d40aa

$ foreman engine status foreman
...
Recent commands (1):
- [completed] stop_task | id=cmd-9f1c2a7b41e0 | task=task-49 | by=carla | at=2026-09-04T12:31:08.402Z
    Stopped task 'task-49': the agent process group was terminated, its run
    settled as killed, and the task is blocked (Stopped by carla).
```

The task is now `blocked` with `blocked_reason = "Stopped by carla"`, its run is
`killed`, and the engine is still resident and ready for the next task.

See [ADR-0011](adr/ADR-0011-resident-engine-and-project-lock.md).

---

## 24. Worktrees

**Foreman never changes what is checked out in your repository.** Every task
runs in its own git worktree that Foreman creates, owns, and deletes.

```
<repo>/.foreman/worktrees/FOR-102/       # one per task, on the task branch
<repo>/.foreman/worktrees/_integration/  # shared, always on the default branch
```

`.foreman/` is already ignored, so those trees never show up in your
`git status`. Set `worktree_root` to move the whole layout somewhere else (an
absolute path puts it on another filesystem).

### What runs where

| Step | Working directory |
|---|---|
| developer, reviewers, architect (native role steps) | the task's worktree |
| `_builtin:run_tests` | the task's worktree |
| refresh-before-develop, conflict-recovery merges | the task's worktree |
| `_builtin:merge` (`--no-ff` into the default branch) | the integration worktree |
| context projection | your `context_dir` **and** the worktree's own `.foreman/` |

### What your checkout sees

Never touched: your current branch, your index, your working-tree files, your
stash. Changed: **refs** — the default branch advances when a task merges, and
task branches appear and move. If you are sitting *on* the default branch when
a task merges, the ref moves under you exactly as a `git fetch` would move a
remote-tracking branch; your files are untouched but now describe an older
commit, so `git status` will show them as behind. `git checkout <branch>` or
`git reset --hard <branch>` when you want to catch up.

### Lifecycle

A worktree is created on a task's first develop visit — from the existing task
branch, or a new one cut from the default branch. It is **kept** across human
gates, quota pauses, review rounds, and engine restarts: resuming at the same
step is only useful if the tree is still there. It is removed when the task is
marked done, when you cancel or delete it, and by `foreman worktree prune`.
Removing a worktree never removes the branch.

`foreman task show <task-id>` prints the path, and so does the dashboard's task
drawer. The path is persisted in `tasks.worktree_path`.

```bash
foreman worktree list <project-id>
# Worktrees
# Root: /repo/.foreman/worktrees
# - FOR-102 | branch=feat/task-worktrees | task=FOR-102 | status=in_progress
#   /repo/.foreman/worktrees/FOR-102
# - _integration | branch=main | role=integration
#   /repo/.foreman/worktrees/_integration

foreman worktree prune <project-id>   # done/cancelled tasks + dangling entries
```

### Giving each worktree its own environment

A worktree is a clean checkout: it has none of your ignored local build state.
If your `test_command` needs a virtualenv or `node_modules`, the fresh tree
does not have one, and `_builtin:run_tests` fails with a "no such file or
directory" for your interpreter — a confusing first symptom of a missing
setting.

**`worktree_setup_command` is how you fix that.** It is a shell command run
once inside each newly created tree, before any step runs there, with the tree
as its working directory:

```bash
foreman config <project-id> --set \
  'worktree_setup_command="$FOREMAN_REPO_PATH/venv/bin/python" -m venv venv && ./venv/bin/pip install --quiet setuptools wheel && ./venv/bin/pip install --quiet -e .'
```

These variables are exported for it:

| Variable | Meaning |
|---|---|
| `FOREMAN_WORKTREE_PATH` | the tree being provisioned |
| `FOREMAN_REPO_PATH` | your checkout — use it for the base interpreter or toolchain |
| `FOREMAN_WORKTREE_BRANCH` | the branch checked out in the tree |
| `FOREMAN_DEFAULT_BRANCH` | the project's default branch |

It runs **once per tree**, not once per step, tracked by a marker inside the
tree's git admin directory (so it never dirties the tree). Change the setting
and every tree reprovisions on its next visit. `worktree_setup_timeout_seconds`
caps it (default 1800; `0` disables the timeout).

The shared `_integration` tree is not provisioned — only the merge runs there,
and it needs git rather than your toolchain.

If the command fails, the task does not run in that tree: an environment that
was never built produces test failures that describe the environment rather
than the task. The tree is left on disk for you to inspect, and the next visit
retries.

> **Anything the command creates must be gitignored.** A tree with untracked
> files is dirty, and a dirty task tree blocks `_builtin:merge`. `venv/`,
> `node_modules/`, and `*.egg-info/` are already in most `.gitignore` files;
> check yours before pointing this at something exotic.

#### The alternative: `worktree_link_paths`

`worktree_link_paths` names repository-relative paths that Foreman *symlinks*
from your checkout into every new worktree:

```bash
foreman config <project-id> --set 'worktree_link_paths=["node_modules"]'
```

It costs nothing, but the tree then **shares** your environment rather than
having its own: a task that upgrades a dependency to make its tests pass
changes your interpreter and every other task's. Use it for tooling that is
expensive to build and genuinely read-only; prefer `worktree_setup_command`
for anything a task might modify. This repository uses the setup command above
and leaves `worktree_link_paths` empty.

### Bounding disk use

One live task means one full checkout, plus whatever `worktree_setup_command`
builds inside it. Several tasks paused at gates used to mean several of each,
with nothing but a manual prune to give the space back.

**`max_live_worktrees` (default 4) caps how many task worktrees exist at
once.** Set `0` to disable the cap.

```bash
foreman config <project-id> --set max_live_worktrees=8
```

The engine enforces it just *before* it creates a tree, so the cap bounds peak
disk use. It reclaims, in order:

1. never the integration tree, and never the tree of the task about to run,
2. trees of done, cancelled, and deleted tasks first,
3. then the least recently used of the rest.

**A tree with uncommitted changes is never reclaimed.** That work is not on the
branch, so removing the tree would destroy it. Everything else is safe to take:
the task keeps its branch and its place in the workflow, and its next visit
recreates the checkout — and reprovisions its environment — from the same
branch. The only cost of being reclaimed is one checkout and one setup run.

So the cap is a ceiling the engine reaches for, not one it can always hold. If
every candidate tree is dirty, the project sits above its cap and the engine
records `engine.worktree_limit_exceeded` naming the trees it refused to take.
Losing an agent's unfinished work to a disk limit would be worse than exceeding
the limit and saying so.

| Event | Meaning |
|---|---|
| `engine.worktrees_reclaimed` | trees removed to make room, and the new count |
| `engine.worktree_limit_exceeded` | the cap could not be met; the dirty trees that blocked it |
| `engine.worktree_reclaim_failed` | reclaiming errored; the task still got its tree |

To reclaim on demand rather than waiting for the cap, use
`foreman worktree prune <project-id>` or the dashboard control below. Both drop
only done, cancelled, and unclaimed trees, so neither can take a tree a live
task is using.

### From the dashboard

Open **Settings → Task working copies** to inspect retained task checkouts
and their disk-use limit. These are separate values, not an agent-concurrency
counter. The folder path is available under **Storage details**.

```
Stored copies              2
Configured storage limit   4
[ Remove unused copies ]
```

Remove unused copies runs the same policy as `foreman worktree prune`. The count excludes the
shared integration tree, which is never pruned.

### Refusals

`foreman run` and `foreman serve` refuse to start when the worktree root is not
ignored by git, or when git is too old for `git worktree` (< 2.5). Both name the
fix. The check runs once, before any task is leased, so you never discover it
halfway through a step.

See [ADR-0012](adr/ADR-0012-worktree-per-task.md).

---

## 25. Intake API

The CLI and the dashboard both assume a person and a sprint. The intake
endpoint is the door for everything else: an incident tracker, a chat bot, a CI
job. One `POST` files a task; Foreman decides where it lands.

### The token

Intake is authenticated by a **project API token**, not the dashboard's shared
token. The two are deliberately separate credentials: the dashboard token is a
session key every holder shares, while an API token is named, scoped to one
project, revocable on its own, and recorded on every task it files.

```bash
./venv/bin/foreman token create foreman --name pagerduty
```

```
API token created
Project: foreman | Foreman
Token: tok-3e69a2a2649c | pagerduty
Scopes: intake

  fmn_M2jJs9H9bkn9-C3u471JJwfFg51jIiJw1CH1L1ONceA

This secret is shown once and is not stored — only its SHA-256 is.
Copy it now; if it is lost, revoke this token and create another.
```

The secret is shown exactly once. Only its SHA-256 reaches SQLite, so a stolen
database yields no usable credential and there is no "show me the token again".
Lost it? `foreman token revoke` and create another.

- `foreman token list <project>` shows id, name, scopes, creation, and last
  use — never a secret.
- `foreman token revoke <project> <token-id>` is a timestamp, not a delete: the
  row stays so old tasks' `created_by = "api:<name>"` still resolves.
- The only scope today is `intake`. `--scope` is repeatable, and the column
  stores a list, so later scopes need no migration.

### Filing work

```bash
curl -sS -X POST http://localhost:8000/api/projects/foreman/intake \
  -H "Authorization: Bearer $FOREMAN_INTAKE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "title": "Disk full on web-3",
        "description": "web-3 crossed 98% disk; the log rotation job is not running.",
        "acceptance_criteria": "Free space stays above 20% for 24h.",
        "task_type": "fix",
        "source": {
          "system": "pagerduty",
          "external_ref": "INC-42",
          "url": "https://pd.example.com/incidents/INC-42",
          "reporter": "ana"
        }
      }'
```

| Field | Required | Notes |
|---|---|---|
| `title` | yes | |
| `description` · `acceptance_criteria` | no | free text |
| `task_type` | no | defaults to `fix` (not `feature`: most work arriving from outside is a problem report) |
| `priority` · `complexity` | no | integer; `small`/`medium`/`large` |
| `source` | no | `system`, `external_ref`, `url`, `reporter` — all strings |
| `sprint_id` | no | omit to use the intake queue |

The response is the task exactly as `GET /api/tasks/{id}` serializes it, plus
`created`. **201** with `"created": true` means a new task; **200** with
`"created": false` means this work was already filed.

### Idempotency

Intake is idempotent on `(project, source.system, source.external_ref)`. Post
the same incident five times — because your webhook retried, or the alert
re-fired — and there is one task. A caller that sends no `source.system` or no
`source.external_ref` has given Foreman nothing to match on, so every call
files new work; send both if you want the guarantee.

A repeat returns the existing task **unchanged**. Intake does not edit tasks:
a second call with a different title does not rename the first.

### Where the task lands

With `sprint_id`, the named sprint (it must belong to the project). Without it,
the project's **intake queue**: a sprint per project, id `<project>-intake`,
titled "Intake queue", created on first use.

Sprints stay the unit of grouping, so a continuous queue is simply a sprint
that never completes. The queue is `active` when the project has no active
sprint and `planned` when one is already running — intake must not displace the
sprint a team is mid-way through. A `planned` queue activates on the next
intake once the active sprint finishes, so queued work never strands. To the
resident engine an active intake queue is an ordinary sprint: it picks up
`todo` tasks there exactly as it would anywhere else.

**The `triage` policy decides the arriving status** (§14), resolved for the
task's type:

- `human` (the default) — the task lands in **`triage`**. The engine never
  selects a `triage` task, and one `engine.attention_needed` turn with trigger
  `triage` is raised so a person sees it. Accept it with `foreman task accept
  <task-id>`, `POST /api/tasks/{id}/accept`, or the board's **Accept** button;
  cancel it with `foreman task cancel`.
- `auto` — the task lands in `todo` and the engine may pick it up on its next
  pass, with no person involved.

```bash
# Trust CI to file runnable work, but keep a person on everything else:
foreman config <project-id> --set policy_rules='{"chore": {"triage": "auto"}}'
```

The `intake.task_created` event records the resulting `status` and the resolved
`triage` decision with its source.

### The audit trail

Every intake task records where it came from:

- `created_by` is `api:<token name>` — `api:pagerduty` above,
- `source_system`, `source_ref`, `source_url`, and `reporter` are columns on
  the task, returned as `source` in the API and shown in the dashboard's task
  drawer (the reference links back when a `url` was sent),
- an `intake.task_created` event on a synthetic `intake` run carries the source
  and the token's **id and name**. The secret appears in no row and no event.

### Errors

| Status | Meaning |
|---|---|
| **401** | No bearer token, an unknown or revoked one, or the dashboard's shared token (it is not accepted here) |
| **403** | A live token belonging to another project, or one without the `intake` scope |
| **400** | Missing `title`, an unknown `task_type`/`complexity`, or a malformed `source` |

A project API token is refused with **403** on every other `/api` route,
whether or not a dashboard token is configured — a leaked intake token can
never be replayed as a dashboard session.

See [ADR-0013](adr/ADR-0013-intake-endpoint-and-api-tokens.md) and
[ADR-0014](adr/ADR-0014-autonomy-as-policy.md).

---

## 26. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| One failed run with `preflight_failed: true` | Backend executable missing or a required `[agent.env]` `env:NAME` var is unset. Install/repair the backend or export the variable; no retries were consumed. |
| Task blocked with `engine.completion_guard` | The merge proof gate failed (weak/docs-only/criteria). Strengthen the change, or `foreman waive-merge` for a criteria-only block. |
| Task blocked at a step with `workflow.loop_limit` | The step bounced `> max_step_visits` times. Inspect `foreman history`; raise `max_step_visits` only if the loop is legitimately long. |
| Manager chat "forgot" recent state | It shouldn't — the state header is regenerated each turn from the DB. If stale, confirm the dashboard is hitting the right `.foreman.db`. |
| `meta/supervise` returns 409 | The `engine.attention_needed` event was already consumed by a prior supervision turn (idempotency guard). |
| Cost shows `$0.00` but tokens are counted | Expected for third-party Anthropic-compatible endpoints; see `zero_cost_token_runs` in totals. |
| Dashboard header says "not running" while work is happening | Residency is the engine lease. A `foreman run` that crashed leaves the lease until it expires (120 s); an engine started outside the dashboard shows as resident as soon as it takes the lock. |
| Dashboard Pause seems to do nothing | `pause` is queued, not signalled. Check `foreman engine status <project>`: a `pending` command means no engine is resident to apply it, and it will be rejected as stale when one starts. |
| `Another Foreman engine is already running project ...` | A resident `foreman serve` (or another `run`) holds the project engine lock. Stop it with `foreman engine shutdown <project>`, or wait out its 120 s lease if the holder was killed. |
| `serve` never picks up a queued task | Check the task is `todo` in the **active** sprint and its dependencies are satisfied. `serve.idle` with `stop_reason` tells you which. |
| SSE/watch feels laggy | Both gate on `PRAGMA data_version` at 0.25 s; they only re-query after another connection commits. A same-process writer won't bump it, but those loops never write. |
| Run refuses to start: "git does not ignore …" | The worktree root would be committed. Add `.foreman/` to `.gitignore`, or point `worktree_root` somewhere ignored (§24). |
| `_builtin:run_tests` fails with "no such file or directory" | The test command needs ignored local state the fresh worktree does not have. Set `worktree_setup_command` to build it (§24). |
| `worktree_setup_command failed with exit code …` | The tree's environment could not be built, so no step ran in it. The tree is still on disk — reproduce the command there by hand. Fixing the setting reprovisions every tree on its next visit. |
| A task's tests pass in your checkout but fail in its worktree | The tree has its own environment now. Something your checkout has is missing from `worktree_setup_command` — or the tree is correct and your checkout is stale. |
| `engine.worktree_limit_exceeded` in the event stream | Every reclaim candidate had uncommitted work, so the cap yielded rather than destroying it. Finish or cancel those tasks, or raise `max_live_worktrees` (§24). |
| A paused task's worktree disappeared | It was reclaimed under `max_live_worktrees`. Nothing was lost — the tree was clean, so its branch has everything, and the next visit recreates it (§24). |
| Your checkout suddenly shows a large uncommitted diff | You are sitting on the default branch and a task merged into it, so the ref moved under you. `git checkout main` (or `git reset --hard main`) to catch up; your files were never modified. |
| Intake answers 401 with a token you just created | The dashboard's shared token was sent instead of the project API token — intake takes only the `fmn_…` secret from `foreman token create`. |
| Intake answers 403 | The token is live but belongs to another project (or lacks `intake`). `foreman token list <project>` shows which project's tokens exist. |
| A route other than intake answers 403 with "only valid on … /intake" | An `fmn_…` API token was sent to a dashboard route. Use the dashboard token there. |
| Intake keeps returning 200 and never creates a task | It is idempotent on `(system, external_ref)`: that pair was filed before. Send a new `external_ref`, or omit `source` to force a new task. |
| Intake tasks are filed but never run | The intake queue is `planned` because another sprint is active. Complete or cancel that sprint — the next intake activates the queue — or activate `<project>-intake` yourself. |
| `.foreman/worktrees/` keeps growing | Trees of tasks that never reached `mark_done`. Lower `max_live_worktrees`, or run `foreman worktree prune <project>` (or Settings → Task working copies → Remove unused copies) to remove anything done, cancelled, or unclaimed. |

---

*Generated as part of the review-roadmap closeout. Keep this manual current when
CLI flags, settings, roles, workflows, or API endpoints change.*
