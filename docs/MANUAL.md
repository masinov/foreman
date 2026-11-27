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

### What a step did to the repository (ADR-0038)

When an agent step ends, the engine compares the task branch's head with the
head just before the agent started (after any branch refresh) and, when they
differ, records `engine.step_changes` on the run: `from_sha`, `to_sha`,
`files` (`path`, `added`, `removed`, `status` of `added`, `modified`,
`deleted` or `renamed`; null counts for a binary file; at most 200, with
`files_total`), `added` and `removed`, and `from_default_branch`. A landed
merge adds `target_before`, `commits` (`sha`, `subject`, oldest first, at
most 50, with `commits_total`) and `changes` to `engine.merge`. A git read
that fails leaves its field out and never fails the step. The step's panel
on the Activity tab shows these as Changed, Main before and Brought in, and
Session ("New", or "Continued from attempt N", read from the runs' stored
session ids). A step recorded before this shows none of them.

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

Roles and workflows are **declarative TOML** (`foreman/data/roles/*.toml`,
`foreman/data/workflows/*.toml`), not hard-coded. Both **Claude Code and Codex** are
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

The engine runs one task at a time (ADR-0039). A task stopped at a gate for
your decision (a merge approval, say) holds the queue: no other task starts
until you decide, and then that task is merged before the next one starts,
from the default branch it left. A run that stops there reports
`waiting_for_decision`. A task blocked by a failure does not hold the queue.

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
| **Role System** | `foreman/definitions/roles.py`, `foreman/data/roles/*.toml` | Declarative agent identity: backend, model(s), tools, prompt template, env. |
| **Workflow Engine** | `foreman/definitions/workflows.py`, `foreman/data/workflows/*.toml` | The state machine: steps, outcomes, transitions, gates, fallback. |
| **Orchestrator** | `foreman/engine/orchestrator.py`, `foreman/engine/` | Ties it together: selects tasks, builds prompts, runs steps, resolves transitions, enforces gates, persists everything. |

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

### What an agent is given (the runner)

A Claude Code agent starts in the task's worktree. It is given that
worktree's own `CLAUDE.md` and `AGENTS.md`, once each (the main checkout's
copies are not loaded), and the prompt Foreman builds. It is **not** given the
operator's Claude Code memory: the runner starts every Claude Code agent, and
the manager's sessions, with `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, so the notes
under `~/.claude/projects/<repository path>/memory/` are not loaded and Claude
Code does not write to them. An agent with Bash or Write runs as your user,
though, and could still write those files on purpose: the setting stops the
loading, not the access. (`--bare` is not used: it also stops `CLAUDE.md`
loading.) A role's `[agent.env]` can set the variable back to `0`.

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
  `branch_name`, `depends_on_task_ids`,
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
or `development_tiered` as needed, or a workflow the workspace defines. Run
again on a project that is already registered, `foreman init` keeps the
workflow the project has, whether it is shipped, the workspace's or the
project's own. The workflow and its roles are checked against the roles and
workflows that project runs with (its own over the workspace's over the
shipped ones, ADR-0024). An unknown id fails with `Unknown workflow: <id>`.

Settings › Runners (`GET /api/v1/runners`) lists, for each agent program, the
models roles use as each project resolves them: the shipped roles with the
workspace's and then each project's own laid over them. A model that only an
override uses is listed; a shipped model no role uses any more is not.

### Sprints

```bash
foreman sprint add <project-id> --title TITLE --goal GOAL
foreman sprint activate <sprint-id>
foreman sprint list <project-id>
foreman sprint complete <sprint-id>
```

`sprint activate` also reopens a finished sprint (the dashboard's "Reopen
sprint"), when no other sprint is active. A cancelled sprint cannot be
reopened.

### Tasks

```bash
foreman task add <project-id> --title TITLE --criteria CRITERIA \
    [--type TYPE] [--description DESC] [--sprint SPRINT_ID] \
    [--depends-on id1,id2] [--rests-on PATH[#HEADING] ...] [--label NAME ...]

foreman task override <task-id> \
    [--step STEP=MODEL ...] [--ladder-start MODEL] \
    [--gate POLICY=auto|human] [--triage auto|human] \
    [--notification none|attention|all] [--clear]

foreman task list <project-id> [--sprint SPRINT_ID] [--rests-on PATH[#HEADING]]
foreman task show <task-id>           # task + worktree + recent runs + events
foreman task accept <task-id>         # triage → todo
foreman task block <task-id> --reason "..."  # only a task that has not started; a started one is stopped or closed
foreman task unblock <task-id> [--reset-visits]
foreman task done <task-id> --reason "..."   # finished outside the engine; nothing is checked
foreman task reopen <task-id>         # done or cancelled → todo, workflow from the start
foreman task edit <task-id> [--title T] [--type TYPE] [--priority N]
                            [--description TEXT | --description-file PATH|-]
                            [--criteria TEXT | --criteria-file PATH|-]
                            [--edit description|criteria]
                            [--rests-on PATH[#HEADING] ...] [--no-rests-on]
                            [--label NAME ...] [--remove-label NAME ...]
                            [--restamp PATH[#HEADING] ...]
                            [--depends-on ID ...] [--no-dependencies]
                                      # what it waits for can change only before it starts
foreman task cancel <task-id>         # also removes the task's worktree
```

Wherever a command takes a task, give its id or its key (`FOR-56`). A key is
unique within a project; one that several projects carry is refused, naming
them, and you give the id instead.

`task edit` changes what the dashboard's Edit changes, through the same
mutation, and a change to a task an agent is working on is recorded as
`human.task_edited` (via `cli`). A text comes one of three ways: on the line
(`--description TEXT`, `--criteria TEXT`; an empty text clears it, as in the
dashboard), from a file or standard input (`--description-file PATH`,
`--criteria-file -`; the way for long texts and scripts), or in your editor
(`--edit description` or `--edit criteria`, one field per run). The editor is
`$VISUAL`, else `$EDITOR`, else `nano`, else `vi`; it opens a temporary file
holding the current text, and closing it unchanged or emptied changes nothing
("Description unchanged."). It opens only with `--edit` and only on a
terminal; elsewhere the command refuses and points to `--description-file -`.

**Documents a task rests on.** `--rests-on PATH` or `--rests-on PATH#HEADING`
(repeat for several; on `task add`, `task edit` and `backlog add`) names a file
of the repository the work is judged against, such as an ADR section or a spec
heading. The path must be a file on the project's default branch, or the
command is refused saying so. Foreman records that branch's commit when each
is named (never typed); `task edit --rests-on` replaces the list, and a
document already on it keeps the commit it was named at, also when only its
heading changes; `--no-rests-on` clears it. A path with a `#` in it is written
with a space before the heading's `#`: `--rests-on "docs/a#b.md #Heading"`, or
`"docs/a#b.md #"` for the whole file. A directory or a symbolic link is refused. The task page's Overview lists them with their commits and opens
each as it was then, and every agent step is given them as pointers: path,
heading and commit, not the text (ADR-0041 section 6).

**Labels.** A task carries labels, the names a project gives in its `labels`
setting (`foreman config <project-id> --set labels='{"ui": "changes what a person sees"}'`).
`--label NAME` (repeat for several) gives them on `task add` and `backlog add`;
on `task edit` it adds one to what the task has, and `--remove-label NAME` takes
one off (also one the project no longer names). A label the project does not name
is refused, and the refusal lists the names it does. Removing a label from the
setting edits no task: it keeps the label, and the task page shows it as
"(unknown)" in the muted `Labels:` line under its title. The dashboard API
returns `labels` and `unknown_labels` on a task and takes `labels` (the whole
list) when a task is created, filed or edited. Routes read them as the fact
`label:<name>` (ADR-0041 section 1).

**When a document it rests on changes.** A merge that changes a document that a
task in triage, todo, in progress or blocked rests on (in a sprint or in the
backlog, a paused one too) adds one line per changed file to
that task's Activity ("docs/adr/ADR-0041.md changed in FOR-80's merge (abc1234)
since this task named it at def5678"), the task page's "Rests on" says so and
links "See what changed" (the diff between the two commits), and the task's next
agent step is told in a section "Changed since this task was planned". The task
is not changed or stopped; a person or the manager decides. Once read, the
document is marked as read: "Mark as read at <commit>" beside it on the task
page, or `foreman task edit <task-id> --restamp PATH[#HEADING]`, stamps that
entry with the default branch's commit now, which clears the notice.
`foreman task list <project-id> --rests-on PATH` (or `PATH#HEADING`) lists every
task that rests on a document, finished, cancelled and backlog ones included,
so a person who supersedes an ADR sees what was built on it.
A text option with its `-file` form, `--edit` with an option for the same
field, and two texts from `-` are refused. The command prints which fields
changed, with a text counted in characters, never printed.

A task an agent filed while working on another says so: `foreman task show` prints
"Filed by the developer while working on FOR-12", and the task's Overview
says the same under Details, with FOR-12 linking to the filing step on that
task's Activity. If that task has since been deleted it reads "while working
on a task that no longer exists". Tasks filed by a person or another system
show nothing new.


`task done` is for work that was finished without the engine (merged by hand,
done elsewhere). It runs none of the task's remaining steps and verifies
nothing; the reason is recorded and shown on the task as "Marked done by
hand". It refuses a task an engine is running, a task in the backlog and a
task that is already closed, and leaves the worktree for `worktree prune`.
`task reopen` refuses a task whose sprint is finished.

### Backlog

Work that is filed or accepted and not yet planned into a sprint (ADR-0021).
The engine never runs it, and it is not listed among sprints. Work flows one
way: filed, accepted, planned.

```bash
foreman backlog list <project-id> [--status filed|accepted|declined] \
    [--query TEXT] [--limit N] [--offset N] [--json]
foreman backlog add <project-id> --title TITLE [--type TYPE] [--criteria C] \
    [--description D] [--rests-on PATH[#HEADING] ...] [--label NAME ...] \
    [--priority N] [--accept]
foreman backlog accept <task-id>      # filed → accepted (same as task accept)
foreman backlog decline <task-id> [--reason TEXT]
foreman backlog plan <project-id> <task-id>... --sprint SPRINT_ID
foreman backlog plan <project-id> <task-id>... --new-sprint TITLE [--goal G]
foreman backlog unplan <task-id>      # a task that has not started goes back
```

`add` files backlog work: what a person files is never a request. Work an
agent (`signal.task_created`) or another system (intake) files follows the
project's `triage` policy (§14): `human` makes it a request, `auto` makes it
backlog work at once. `backlog accept` turns a request into backlog work,
which matters where Foreman starts backlog work itself; `backlog plan` puts
a request or backlog work into a sprint, and planning a request accepts it.

`task unblock` refuses a task parked at a human gate (use `foreman approve` or
`foreman deny` for those) and clears the engine's dead letters — see
[Dead-letter kinds](#dead-letter-kinds). Unblocking resets the step visit
counts and starts the workflow over, except for a task a step's own cap
blocked ([Capping a step](#capping-a-step-max_visits)): that one resumes at the
capped step, its counts kept, and `--reset-visits` (or `reset_visits` in the
API) starts every count over.

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
foreman task override task-123 --step develop=MiniMax-M2 --ladder-start claude-opus-5-5
foreman task override task-123 --gate merge_approval=human --notification all
foreman task override task-123 --triage ""      # drop just that override
```

### Execution

```bash
foreman run <project-id> [--task TASK_ID] [--json-logs] [--db DB]
foreman serve <project-id> [--poll-seconds N] [--once] [--db DB]
```

### Output for other programs, and errors

Every read command takes `--json` and prints one JSON document instead of
text: `projects`, `project`, `status`, `board`, `cost`, `outcomes`,
`history`, `transcript`, `sprint list`, `task list`, `task show`,
`backlog list`, `proposal list`, `proposal show`, `worktree list`,
`token list`, `notify list`, `notify deliveries`, `engine status`, `roles`,
`workflows`, `role list`, `role show`, `workflow list`, `workflow show` and
`db version`. The text and the document come from the same read, the one
the dashboard's API uses where there is one, so they never disagree.
`foreman watch` is a live tail and has no single document.

A command that fails prints one line starting `foreman:` and exits 1. An
error that is a bug in Foreman exits 70 and says so; set `FOREMAN_DEBUG=1`
to get the traceback. An interrupted command exits 130.

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
defaults to the OS user name. A pause stays in force until a `resume`: an
engine restarted while the project is paused starts paused. A `run-task`
command is `acknowledged` while it waits and `completed` once its task has
run. A one-shot `foreman run` also answers these commands while it works; it
stops for `pause`, `shutdown` and `stop-task` and refuses `run-task`. See
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
foreman outcomes <project-id>         # how well the agents do: first-time passes,
                                      # send-backs by cause, a person's part, cost
                                      # per merged task, by role and model
foreman history <task-id>             # run + event history for a task
foreman transcript <run-id>           # full persisted transcript for one run
```

### Introspection & DB

```bash
foreman roles                         # list shipped roles
foreman workflows                     # list shipped workflows
foreman role list <project>            # the roles a project runs with, and where each comes from
foreman role show <project> <id>       # one role as TOML
foreman role set <project> --file F    # save a role for the project (its id is in the file)
foreman role reset <project> <id>      # back to the shipped role
foreman workflow list|show|set|reset   # the same for workflows (ADR-0024)
foreman role list --workspace          # the workspace's defaults: every project without its own version runs with them
foreman role show --workspace <id>     # (also set --file F, reset <id>; the same four for `foreman workflow`)
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
full either way; the mapping lives in `foreman.history.logs.event_log_level`.

`--once` runs exactly one pass and exits, for cron-style deployment and for
tests. Retention pruning and crash recovery run at startup and after any pass
that executed work — never on an idle wake, so an idle engine does nothing
between wakes but re-read `PRAGMA data_version`.

Exit codes: `0` on a clean stop (including SIGTERM), `1` when the lock is
refused, when it is lost to another engine, or on a project-level error.

---


### 6.2 Keeping the worker and the dashboard running (systemd)

`deploy/systemd/` holds two systemd **user** units: `foreman-worker@.service`
(one instance per project, `foreman serve <project>`) and
`foreman-dashboard.service`. Both start at boot and start again after any
exit, a crash or a SIGKILL included, thirty seconds later; after ten starts in
ten minutes systemd gives up, and the dashboard says "no worker" with Restart.
A fault that does not pass ends there: `journalctl` shows the message.
A database whose schema is not this Foreman's (older: run `foreman db
migrate`; newer: upgrade Foreman) is not retried at all: `foreman serve` and
`foreman dashboard` exit with status 78 and the units name it in
`RestartPreventExitStatus=78`, so systemd leaves them stopped. The worker also
writes the reason to its log, `.foreman/serve.log`.
`foreman serve` exits 0 when ended with `foreman engine shutdown`, so the unit
starts it again: ending a worker holds nothing (ADR-0043). A worker started
again takes over the project's engine lock when the dead one's lease has
expired (up to two minutes after a SIGKILL; the starts before that fail and
are retried) and carries on the task it was on, as after any engine restart.

Installing them is your step; Foreman does not do it. From the checkout, with
`foreman` in `./venv/bin`:

```bash
mkdir -p ~/.config/systemd/user
for f in deploy/systemd/*.service; do
  sed "s|@REPO@|$PWD|g; s|@FOREMAN@|$PWD/venv/bin/foreman|g; s|@PATH@|$PATH|g" "$f" \
    > ~/.config/systemd/user/$(basename "$f")
done
systemctl --user daemon-reload
systemctl --user enable --now foreman-dashboard.service foreman-worker@foreman.service
loginctl enable-linger "$USER"     # start at boot, before you log in
systemctl --user status foreman-worker@foreman.service
journalctl --user -u foreman-worker@foreman.service -f
```

The units are given your `PATH` as it is when you run this, so the agent
programs (`claude`, `codex`) are found as they are in your shell; run it again
after one moves. Replace `foreman` in `foreman-worker@foreman.service` with the
project id. Run
`foreman db migrate` before starting after an update (section 20). To remove:
`systemctl --user disable --now <unit>` and delete the file.

A killed worker leaves no agent behind: each agent has a small guard process
that, when the worker's end of a pipe closes, kills the agent's process group
and every process it saw below the agent. Claude Code runs each tool command in
a session of its own, outside the group, so the guard looks at the agent's
process tree every two seconds; a tool started in the last two seconds before
the worker died can be missed. Under the systemd unit, systemd ends everything
left in the unit's control group as well.

## 7. Roles

A role is a declarative TOML file describing one agent identity. Shipped roles:

| Role | Model (default) | Session | Purpose |
|---|---|---|---|
| `developer` | project default | persistent | Implement the change on the task branch. |
| `code_reviewer` | `claude-sonnet-5-5` | ephemeral | Agentic review with repo tools. |
| `security_reviewer` | `claude-sonnet-5-5` | ephemeral | Security-focused review (in `development_secure`). |
| `triage_reviewer` | `claude-haiku-5-5` | ephemeral | Cheap payload-only triage; can `ESCALATE`. |
| `frontier_reviewer` | `claude-opus-5-5` | ephemeral | Tool-less frontier adjudication of a curated diff. |

### Role TOML anatomy

```toml
id = "developer"
name = "Developer"

[agent]
backend = "claude_code"            # or "codex"
model = "claude-sonnet-4-6"        # "" → project default_model
session_persistence = true         # reuse --resume session across runs
permission_mode = "bypassPermissions"
# Optional: models to move up after failures of the step's own work (see §9):
model_ladder = ["claude-sonnet-5-5", "claude-opus-5-5"]
escalate_after = 2                 # failures on one model before the next

# What the agent can use (ADR-0023). A non-empty `allowed` is its whole tool
# set; `disallowed` is taken away on top. Both empty: every tool.
[agent.tools]
allowed = []                       # e.g. ["Read", "Grep", "Glob"] for a reviewer
disallowed = []

# Optional per-endpoint environment (see §9):
[agent.env]
ANTHROPIC_BASE_URL = "https://api.example.io/anthropic"
ANTHROPIC_AUTH_TOKEN = "env:EXAMPLE_API_KEY"
CLAUDE_CONFIG_DIR = "env:EXAMPLE_CONFIG_DIR?~/.foreman/claude-example"

[completion]
# How the engine interprets this role's final message.
[completion.output]
extract_decision = true            # decision role: parse APPROVE/DENY/STEER/ESCALATE
approve_needs_reading = true       # an approval of a cut diff with no file opened is sent back once, then stops the task
approve_needs = "checked"          # a reviewer's approval needs: "checked" (default), "ran" or "stated"

[prompt]
template = """..."""                # supports {task_title}, {acceptance_criteria},
                                    # {completion_evidence}, {completion_diff}, …
```

`{environment_rules}` is filled from the repository's `AGENTS.md`: when it names
a virtual environment (`./venv`, `.venv`), the value is a bullet forbidding the
system `python`, `python3` and `pip` and naming that environment's binaries;
otherwise it is empty. Put it alone on a line; an empty value removes the line.
A role without it renders as before.

**How a reviewer checked each criterion.** A role whose record is a
`review_verdict` lists, for each acceptance criterion, its `status`
(`verified`, `not_verified`, `judgement`) and `evidence`, and three fields of
its basis:

| Field | Type | What it says |
|---|---|---|
| `ran` | list of text | The commands it ran for the criterion, exactly as it ran them. |
| `read` | list of text | The files, or parts of the diff, it read for it. |
| `from_report` | true or false | True when it relied on the developer's report or the test step's output. |

Foreman checks what it can: each command under `ran` is looked for among the
commands it recorded during that review run (the `agent.command` events). A
command that was not run makes the verdict disagree with its outcome, with the
reason ("criterion 2 cites `pytest tests/test_x.py`, which the review did not
run"), and the step is replayed once like any verdict that disagrees. A replay
that resumes the review's session is checked against the whole session. A
cited command counts only when it ran as a whole command, program and
arguments word for word (option flags may differ; a `cd` before it, a pipe
after it and a shell wrapper do not matter): running one test file is not
running the suite. `read` is the reviewer's word.

`approve_needs` in `[completion.output]` says what an approval needs of each
criterion marked `verified`:

- `checked` (the default): a command it ran, a file it read, or the criterion
  marked `judgement` with its reason in `evidence`. A criterion whose only
  basis is `from_report` is not verified.
- `ran`: a command it ran, or `judgement` with its reason.
- `stated`: the reviewer's word, as before.

The reviewer's prompt says its own role's rule. A role that cannot run a
command (no tools, or no Bash) cannot ask for `ran`: the role is refused when
it loads. A reviewer role written before criteria had a basis (its record
declares no `ran`) is taken on its word.

It is a property of the role, set where models are: the workspace's role is
every project's default and a project's own role overrides it (ADR-0024), in
the role's TOML or in Settings › Roles, "An approval needs", shown only for a
role whose record is a `review_verdict`. There is no separate project setting
and no rule per task type. The task page shows each criterion's basis in the
review step's details, the commands as code, and marks the ones Foreman saw
run.

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
a correction that lists the role's own options. A developer that ends
without the marker is asked once the same way. The replay resumes the
agent's session, so it is sent the correction alone, not the task again;
only when there is no session to resume is the first prompt sent with the
correction after it.

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
(`foreman/domain/outcomes.py`): `success`, `failure`, `error`, `killed`, `paused`,
`conflict`, `done`, plus reviewer decisions `approve`, `deny`, `steer`,
`escalate`. Transitions are keyed `completion:<outcome>`. Unknown agent
outcomes normalize to `error` (deterministic fallback).

The merge step (`_builtin:merge`) ends in `success`, `failure`, `conflict` or
`updated` (ADR-0026). `updated` means the branch was behind the default branch,
Foreman merged the default branch into it in the task's worktree and did not
merge the task. A workflow of a project's own needs a transition
`from = "merge"`, `trigger = "completion:updated"`, `to = "test"` (the shipped
workflows have it). Without one the outcome has no transition: the task takes
the workflow's `[fallback]` and blocks, and the `workflow.no_transition` event
names the step and the outcome `updated`.

### Loop protection

Each step visit increments `step_visit_counts[step]`. Exceeding
`max_step_visits` (default 5) blocks the task with a `workflow.loop_limit`
event and a `loop_limit` supervision trigger. The `completion:conflict`
transition explicitly **resets** the visit budget (emitting
`workflow.step_visit_reset`) so conflict recovery doesn't starve the loop.

### Capping a step: `max_visits`

A step may set `max_visits = <n>` (a positive integer):

```toml
[[steps]]
id = "review"
role = "code_reviewer"
max_visits = 2
```

When the task is about to enter the step for the (n+1)th time it is blocked
instead, before the step runs: the reason names the step and its cap ("Review
ran twice, its cap: a person decides."), a `workflow.step_cap` event is
recorded, and the task keeps the step as its resume point. A step's own cap is
checked first; `max_step_visits` stays the overall stop for a loop through a
step without a cap.

The block is a dead letter of the `engine` kind: clear it with
`foreman task unblock` or Unblock on the task page. The step then runs once
more, and the count is **not** reset: the capped step's count drops by one (to
n−1), the other counts stay, and the next entry blocks again. Say
`foreman task unblock <task> --reset-visits` (the API's `reset_visits`) to start
every count over, so the step has its n visits again.

Use `max_visits` when the answer to "it has gone round enough" is a person.
When the workflow has another path at a count (send it to a different step,
or to a person through a gate of its own), put the fact `visits:<step>>=<n>`
on a route instead (see Routes); a cap has no path of its own.

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

### Moving up a role's models

Give a role its models, cheapest first, and how many failures of its own work
on one model it takes to move to the next (ADR-0041; also in Settings › Roles,
for the workspace's roles and a project's own):

```toml
[agent]
model_ladder = ["claude-sonnet-5-5", "claude-opus-5-5"]
escalate_after = 2   # failures on one model before the next; default 2
```

One model (or `model`) never moves up; none uses the project's default.

A step moves up only after `escalate_after` failures of its own work on its
model: its run ended without a result, the review sent the work back with an
S1 or S2 finding, or the tests failed after it. These never count: an engine
restart, a Stop, a send-back after a conflict, tests that fail right after the
merge step brought the branch up to date, a wait for usage limits, an
infrastructure error, a run stopped by a cost or time limit, and a reviewer
that approved unread. Those block the task for a person as before, or run the
step again without counting. After `escalate_after` failures on the last model
the task blocks for a person with the reason. The counts are kept on the task
per step and model; unblocking or reopening the task starts them over. A step
that moves up still has a visit limit: `max_step_visits` plus
`escalate_after` × its number of models.

Every move up is a line in the task's Activity ("Develop moves up to
claude-opus-5-5 · the review sent it back twice"), and `foreman outcomes`
compares models.

### Per-task overrides

A manager differentiates dispatch per task:

```bash
foreman task add <project> --title ... --criteria ...
foreman task override <task-id> --step develop=MiniMax-M2 --ladder-start claude-opus-5-5
```

**Model resolution precedence** (`resolve_step_model_selection`):

1. A model pinned for the step (`--step`): it runs on every visit and never
   moves up.
2. The role's models: the step starts on the task's start model
   (`--ladder-start MODEL`; the role's first when it does not list it) and
   moves up after `escalate_after` failures of its own work on each.
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

### Acceptance criteria

An approving code review of the branch head covers a task's acceptance
criteria. Nothing else checks them: until the review approves, each criterion
is recorded as `unverified` and the proof is pending. An approval of an older
commit does not cover them. The criteria judge, an optional model call that
marked each criterion, was removed on 2026-11-19 (ADR-0010 amendment);
evidence it recorded still loads and shows as it was.

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
- The first turn of a session injects the **operating contract**: the read
  commands, the proposal format, and the hard rules. The manager changes
  nothing itself (ADR-0022): it proposes with `foreman proposal create`, and a
  person confirms. Inside its session (`FOREMAN_MANAGER_SESSION` is set) every
  other state-changing `foreman` command is refused.
- The person's message and an empty reply marked `in_progress` are stored
  *before* the model is invoked. The reply is saved as it grows (at most once a
  second), so anyone with the side bar open sees it being written, and is
  completed when the turn ends, flagged `interrupted` if it broke off. A
  dashboard that starts marks a reply left `in_progress` as interrupted
  (ADR-0022, 2026-11-18).
- One message at a time: while a reply is being written, another message,
  a supervision turn and clearing the conversation are refused.
- The manager's process is killed when its turn ends, however it ends.
- **Start a new conversation** forgets the conversation and declines the
  proposals still waiting in the project. The dialog says how many.
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
builds a compact **attention digest** (`foreman/manager/digest.py`) and runs one
supervision turn through the persisted session:

- the turn is flagged `origin="supervision"`,
- the consumed `event_id` is recorded; a replayed event is rejected with **409**,
- in every project the digest asks the manager to answer or propose; in
  **`directed`** projects it also says it may not run state-mutating commands.

### Proposals: the manager proposes, a person confirms

A proposal is a reason and an ordered list of operations: `create_sprint`,
`edit_sprint`, `activate_sprint`, `finish_sprint`, `file_task`, `accept_task`,
`decline_task`, `plan_tasks`, `unplan_task`, `edit_task`, `block_task`,
`unblock_task`, `cancel_task`, `send_back`, `approve_gate` (ADR-0022 lists the
fields). `create_sprint`, `file_task` and `add_task` take a `ref`, a name that
later operations of the same proposal use wherever they take a sprint or task
id. One proposal can create a sprint and add tasks to it, or file tasks and
plan them into it.

```bash
foreman proposal create <project> --json proposal.json   # or --json - for stdin
foreman proposal list <project> [--state proposed,failed] [--json]
foreman proposal show <proposal-id>
foreman proposal confirm <proposal-id>     # applies it, whole or not at all
foreman proposal decline <proposal-id>
```

`create` checks every operation in order against the project as it is now and
stores nothing if one is refused, saying which and why. `confirm` applies them
in order in one transaction, as you; if one is refused because the project
moved on, nothing is applied and the proposal is marked `failed` with the
reason. In the dashboard a proposal appears as a card in the manager side bar
with **Not now** and **Confirm**.

Auto-invocation policy (poll-and-call vs. a human button) is a frontend/ops
concern — the backend only provides the endpoint.

---

## 13. Autonomy & task selection

Two related knobs:

- **`Project.autonomy_level`** (`directed` / `supervised` / `autonomous`)
  governs how far the engine advances on its own:
  - **`sprint_completion`** setting (`human` / `auto`; in the dashboard,
    "Finish sprints: A user / Foreman", beside "Approve merges"). It alone
    decides who finishes a sprint (ADR-0025 amendment); the autonomy level
    no longer does.
  - `human` (the default) — the engine never finishes a sprint. When every
    task is `done` or `cancelled` the sprint stays
    `active`, the pass stops with `sprint_resolved`, and one `sprint_resolved`
    attention turn (with `engine.sprint_ready`) says it is ready to be
    finished. Both are the sprint's own records, not a task's (ADR-0037).
    The sprint page's State reads "Ready to finish" from its tasks, whether
    an engine runs or not, and Needs you lists it with a Finish button. Later passes
    over the same resolved sprint add nothing; a task added to it is run,
    and the turn is raised again once it is resolved. A person finishes the
    sprint (dashboard "Finish sprint", `foreman sprint
    complete`, or a confirmed `finish_sprint` proposal). The next planned
    sprint then waits for a person to activate it ("Activate sprint",
    `foreman sprint activate`, or Start on the engine row when no sprint is
    active): the engine never starts a planned sprint on its own (owner,
    2026-11-21), so a sprint created while it runs stays planned until its
    tasks are planned and someone starts it.
  - `auto` — completes the resolved sprint (`engine.sprint_completed`),
    activates the next planned sprint and keeps going; when there is none it
    stops `idle` with the `sprint_resolved` turn.
- **`task_selection_mode`** setting (`directed` / `autonomous`; in the
  dashboard, "Foreman starts backlog work: Off / On"): what a person planned
  into the active sprint always runs first. In `autonomous` mode, when nothing
  planned can run, the engine takes the next accepted backlog task into the
  active sprint itself (higher priority first, then the order filed), up to
  `max_autonomous_tasks` per sprint. It never takes a request, which is work
  an agent or another system filed that no person has accepted, and it
  invents no tasks (ADR-0028).

When a sprint resolves and the engine stops (a directed or supervised sprint
left active for a person, or one Foreman finished with no further sprint), it raises a
`sprint_resolved` supervision turn so the manager can decide the next move.

---

## 14. The policy matrix, human gates & merge waivers

### The policy matrix

Autonomy in Foreman is a policy, not a mode. One matrix
(`foreman/domain/policy.py`, ADR-0014) answers every question of the form "does a
person do this?":

| Decision | Values | Default | What it governs |
| --- | --- | --- | --- |
| `triage` | `auto`, `human` | `human` | whether work filed through the intake API (§25) is runnable on arrival, or waits in `triage` for a person |
| `plan_approval` | `auto`, `human` | `human` | who confirms a plan the manager proposes (Plan this sprint, Split into smaller tasks), and a workflow gate that names it |
| `merge_approval` | `auto`, `human` | `auto` (a new project is created with `human`) | the merge gate every shipped workflow ends in |
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

### What the merge gate reads in a review

The merge gate rests on the approving review of the branch head (§10). Foreman
accepts that approval only when the verdict agrees with it: no S1 or S2
finding, each of the task's criteria listed, each one verified or the
reviewer's judgement, and, as the reviewer role's `approve_needs` asks (§7),
each verified criterion resting on a command the review ran (`ran`), or on one
it ran or a file it read (`checked`, the default). A criterion resting only on
the developer's report is not verified, and a command the verdict cites that
the review did not run ends the step as an error.

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

Approve and deny record a decision; they do not run anything. The task moves
to the step the decision leads to and the project's engine continues it. If a
resident engine (`foreman serve`) is running it picks the task up at once. If
none is, the command prints `foreman run <project-id>` to continue, and the
dashboard says the task waits at its step until the engine is started. See ADR-0011.

The dashboard exposes the same via `POST /api/tasks/{id}/approve|deny` and the
gates endpoints.

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
settings endpoint). Validated by `foreman/domain/settings.py`: an invalid value is
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
| `agent_env_passthrough` | `[]` | names of host environment variables given to every agent process on top of the short list all agents get (ADR-0023); for example a database address the tests need |
| `sandbox_allowed_hosts` | `[]` | hosts a review sandbox may reach, as names or `*.example.com`; none by default, `localhost` always works (host-level; §24) |
| `sandbox_read_paths` | `[]` | absolute paths (`~/` allowed) a review sandbox may read although they lie under your home directory or beside the repository: a toolchain, a package cache (host-level; §24) |
| `sandbox_allow_unix_sockets` | `false` | lets a review sandbox's commands create unix sockets, which a browser needs for the screenshots script; the host's `/run` and temporary directories are closed to it (host-level; §24) |
| `sandbox_database_copy` | `false` | gives a review sandbox a copy of this project's records (`.review/live.db`), without other projects, tokens, notification destinations or the manager's conversations (host-level; §24) |
| `write_checkpoint_notes` | `false` | when a sprint is finished, commit a note of its goal, tasks and follow-ups to `docs/checkpoints/<tag>.md` on the default branch before the sprint is tagged (ADR-0036). The tag is made either way |
| `generate_changelog` | `false` | when a sprint is finished, fold the `changes/<task key>.md` files into a section of `CHANGELOG.md` (newest sprint first, above what the file held before) and remove them, in the checkpoint's commit (ADR-0040). Off: the file and `changes/` are left as they are. `foreman changelog <project> [--sprint <id>]` does the same by hand |
| `generate_copies` | `false` | Foreman writes `docs/STATUS.md` and `docs/sprints/current.md` from its database when a sprint starts and when it finishes (in the checkpoint's commit), and a finished sprint's archive copy `docs/sprints/archive/sprint-<n>-<slug>.md` (ADR-0040); a sprint's finish and the command also write `docs/sprints/backlog.md`. An archive file written by hand is never replaced. No task edits them. `foreman copies <project> [--sprint <id>]` writes them by hand |
| `labels` | `{}` | the labels a task may carry: `{"<name>": "<one-line meaning>"}`. A name is lowercase words joined by `-` or `_` (`ui`, `needs-docs`). Set by `foreman config <project-id> --set labels='{"ui": "changes what a person sees"}'`; a bad name or an empty or many-line meaning is refused. Not host-level. Removing one edits no task (see Tasks › Labels) |
| `path_groups` | `{}` | named groups of path patterns, for the routes' facts `changed:<group>` (any changed path is in the group) and `changed_only:<group>` (every changed path is in the listed groups): `{"<name>": ["<pattern>", ...]}`, such as `{"frontend": ["frontend/**"], "docs": ["docs/**", "*.md"]}`. A pattern is gitignore-style and relative to the repository: no `/` in it (`*.md`) matches at any depth, one with a `/` is anchored at the root (`docs/*.md`), `**` crosses directories, a directory matches everything under it. No leading `/` or `~`, no `..`, no `!`. A path in no group counts for none, so it defeats `changed_only:`. Not host-level |
| `adr_dir` | `docs/adr` | the folder whose decisions are numbered when a task merges (ADR-0040): a branch writes `<adr_dir>/new-<slug>.md`; the merge commit renames it to `ADR-NNNN-<slug>.md` (next free number), sets the number in its title line, rewrites references to it and regenerates the folder's `README.md` index from each ADR's title and status (the hand-written part above the list is kept). A merge that would leave two ADRs with one number is refused, naming the files. Empty, or no such folder: left alone |
| `merge_push_remote` | `""` | name of the git remote the default branch is pushed to after each merge (for example `origin`). Empty: merges stay on this machine. A push that fails is recorded (`engine.push_failed`) and the merge stands |
| `worktree_setup_timeout_seconds` | `1800` | wall-clock cap for `worktree_setup_command`; `0` disables the timeout |
| `completion_guard_enabled` | `true` | enforce the merge proof gate |
| `merge_approval` | `auto` | `auto` or `human`: whether the `merge_approval` gate needs a person (§14) |
| `sprint_completion` | `human` | `auto` or `human`: whether the engine finishes a resolved sprint and starts the next (ADR-0025) |
| `plan_approval` | `human` | `auto` or `human`: whether a person confirms a plan the manager proposes (§14) |
| `triage` | `human` | `auto` or `human`: whether filed work is runnable on arrival or waits in `triage` (§14) |
| `notification` | `attention` | `none`, `attention`, or `all`: what the project wants to be told about (§14) |
| `policy_rules` | `{}` | per-task-type policy overrides, `{"<task_type>": {"<decision>": "<value>"}}` (§14) |
| `default_model` | `""` | fallback model when a role pins none |
| `meta_agent_model` | `""` | `--model` for the manager chat session |
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

The backend (`foreman/api/`) is a thin FastAPI transport over the
services (`foreman/services/`, one per area, put together by `Services`); the
services are the only thing that touches the store. Fresh services are
constructed per request and
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
- The **manager chat** runs an agent session with a shell on the server. It is
  enabled on loopback binds and disabled elsewhere (its routes answer **403**)
  unless you pass `--allow-remote-manager`, in which case every token holder
  can run that agent. Its `foreman` commands cannot change project state
  (ADR-0022), but the shell itself is not sandboxed.
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
  `worktree_setup_command`, `worktree_root`,
  `worktree_link_paths`, `context_dir`, `merge_push_remote`,
  `agent_env_passthrough`. Set them
  at a terminal with
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
| `GET /api/sprints/{id}/activity` | what happened to the sprint's tasks, newest first: runs and what a person did by hand; `only=problems` for send-backs, failures and blocks |
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
| `DELETE /api/projects/{id}/meta/session` | clear the manager session; declines the proposals still waiting (`declined_proposals`) |
| `GET /api/projects/{id}/proposals` | the manager's proposals, newest first (`state`, `limit`, `offset`) |
| `GET /api/proposals/{id}` · `POST /api/proposals/{id}/confirm\|decline` | read, apply or decline one proposal |
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
- `foreman outcomes <project-id> [--sprint <sprint-id>] [--json]` — outcome
  numbers (ADR-0034), also `GET /api/v1/projects/{id}/outcomes?sprint=`:
  - **Tasks:** started, merged by the engine, closed by hand, cancelled, not
    finished. A task filed and never run is not counted.
  - **Passed first time:** merged with no send-back; a second figure leaves
    merge conflicts aside, since those are usually caused by other work.
  - **Send-backs:** each return to the step that builds the change, by
    cause: `tests`, `review` (and which reviewer), `person` (a send-back at
    a gate), `merge_conflict`.
  - **A user:** decisions a gate asked for, with the median wait and how
    many still wait; and times a person stepped in unasked (a note, an
    edit, a block, a cancel, closing by hand, reopening).
  - **Cost:** in total, per merged task, and on tasks not merged; tokens per
    merged task, split into input, output, cache read and cache write.
  - **Time to merge:** median, from the first step to the merge.
  - **By role and model:** runs, failed runs, cost and tokens; send-backs a
    reviewer caused, on the model it ran; and for the role that builds, the
    tasks it built that merged and how many of them passed first time,
    credited to the model of the task's first build.

  The numbers are computed from the kept runs and events, so a project that
  prunes its history loses the pruned part from them.

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
  `sprint_started`/`sprint_ready` (a directed or supervised sprint is fully resolved and waits for a person)/`sprint_completed` (autonomous projects only), `attention_needed`,
  `crash_recovery`, `event_pruned`/`run_pruned`, `test_run`/`test_output`,
  `command_applied`/`command_rejected` (one per engine command, carrying
  `command_id`, `command`, `requested_by`, `task_id`, and `detail`).
- **`intake.*`** — `task_created`, one per task filed through the intake API
  (§25), on a synthetic `intake` run. Carries the `source` object, the task
  key, the sprint it landed in, and the filing token's `token_id` and
  `token_name` — never the secret.
- **`gate.*`** — `cost_exceeded`, `time_exceeded`.
- **`signal.*`** — agent-emitted signals the engine consumes: `task_created`,
  `blocker`.

---

## 20. Database & migrations

The schema evolves through an **append-only** migration ledger
(`foreman/store/migrations.py`): a list of `(version, description, sql)` tuples applied
in order and tracked in `schema_migrations`. Never renumber or rewrite a landed
migration.

```bash
foreman db version          # current applied schema version
foreman db migrate          # apply any pending migrations
```

**Upgrade steps.** Migrating is a deploy step: stop `foreman serve` and the
dashboard, update Foreman, run `foreman db migrate`, start them again. The
store no longer repairs the schema when it opens. **Only `foreman db migrate`
migrates.** Every other command (`foreman run`, `foreman backlog list`, `foreman
task show`, and the worker and dashboard) creates a new database at the latest
version but refuses an existing one at another version, and changes nothing in
the file, with a message naming what to do: run `foreman db migrate` when it is
older than the code, upgrade Foreman when it is newer (a database cannot be
taken back). `foreman serve` and `foreman dashboard` then exit with status 78,
which the systemd units do not restart (section 6.2).

A command finds its database in the repository it runs in, never in a parent
of it: the search stops at the first directory with a `.git`, and at
Foreman's runtime directory `.foreman/`. A task worktree or sandbox under
`.foreman/worktrees/` finds none unless given `--db` or `FOREMAN_DB`, and
says so. Code an agent wrote never gets `FOREMAN_DB`, even when the engine's
own environment has it: not the agent, not the test command, not the
worktree setup command. A project cannot pass it through
(`agent_env_passthrough` refuses it), and `worktree_link_paths` refuses the
database, `.foreman/` and `.git`.

Each migration is applied atomically: its statements and its ledger row run
inside one `BEGIN IMMEDIATE` transaction, so a failing migration leaves the
database at the previous version and raises `MigrationError`. Two processes
that initialize the same database at once cannot double-apply a version.

File-backed databases open in WAL mode with `synchronous=NORMAL` and a 30 s
busy timeout so the engine, the dashboard, and the CLI can share one file.
Expect `.foreman.db-wal` and `.foreman.db-shm` sidecar files next to the
database; scaffolded repositories ignore them. WAL needs a local filesystem.

Recent migrations:

| # | Contents |
|---|---|
| 11 | `meta_sessions`, `meta_turns` + index (manager persistence) |
| 12 | `tasks.executor_overrides_json`, `tasks.complexity` (dropped by 33) |
| 13 | `projects.task_key_prefix`, `tasks.task_key` (Jira-style keys) |
| 14 | gate tables rebuilt with `ON DELETE` rules, `events(task_id, timestamp)` index, `projects.task_key_seq` + unique task keys |
| 15 | `engine_commands` + `(project_id, status, requested_at)` index (the control channel to a resident engine) |
| 16 | `tasks.worktree_path` (the Foreman-owned checkout a task runs in) |
| 17 | `api_tokens` + unique `token_hash` index; `tasks.source_system`/`source_ref`/`source_url`/`reporter` + `(project_id, source_system, source_ref)` index (intake, §25) |
| 22 | `proposals` + `(project_id, created_at)` and `turn_id` indexes (the manager's proposals, ADR-0022) |

---

## 21. Validation

```bash
# Repo-memory scaffold checks
./venv/bin/python scripts/validate_repo_memory.py

# Full backend suite, one worker per core
./venv/bin/python -m pytest tests -n auto -q

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

So a resident engine (the project's worker) takes messages through a table.
`engine_commands` is the **only** channel to a worker: the CLI, the
dashboard, and the intake API all write rows to it, and whichever worker
holds the project lock consumes them. The row is the audit trail — it records
who asked, when, and what the worker did about it.

Whether the work may go on is not a message to a worker: it is a user's holds
on the work (ADR-0043, "Holds on the work" below), which every worker reads.

### The commands

| Command | Effect |
|---|---|
| `run_task <task-id>` | Run that task next, regardless of sprint order. Refused for a task a user holds. |
| `steer_task <task-id>` | Interrupt the running agent step of that task so it starts again with a user's guidance. |
| `shutdown` | Cut the running step (its task stays resumable), release the lock, exit 0. The work stays as it is: another worker carries on with it. |

`pause`, `resume` and `stop_task` were retired by ADR-0043. A worker that
finds one rejects it, saying where it went.

### Holds on the work

| | Pause | Block |
|---|---|---|
| On | a task; a sprint's or the workspace's Pause pauses each unfinished task there | a task, a sprint, or the workspace |
| A running step | finishes first (`--now`, Stop: is cut, and runs again on Resume) | finishes first |
| Lifted by | Resume, on the task or on any level above | Unblock, where it was set |
| In Needs you | no | yes, with its reason |

A held task is skipped when the worker chooses the next task (it does not
hold the queue), and parked before its next step, built-in steps included, so
it never merges or becomes done. What waits for it waits too, its sprint is
not finished, and the next sprint does not start. A blocked sprint or
workspace holds everything in it the same way. A cut visit does not count
against the step's visit limit.

```bash
foreman pause <project> --task FOR-56 [--now]   # or --sprint <id>; --all for the workspace
foreman resume <project> --sprint <id>          # or --task, or --all
foreman block <project> --sprint <id> --reason "..."   # or --all
foreman unblock <project> --sprint <id>         # or --all
```

### Lifecycle

Every command moves `pending` → `acknowledged` (the engine has picked it up) →
`completed` or `rejected`, always with a `result_detail` explaining the
outcome, and always leaving an `engine.command_applied` or
`engine.command_rejected` event behind — on a system run for the task involved,
or on a project-level run when no task is involved.

Rejections are ordinary, not errors. A `run_task` naming a task that is
`blocked`, `done`, held, or owned by another project is rejected with the
reason.

### When no engine is resident

A command that describes *work* outlives the process, so a pending `run_task`
is honoured by the next worker to start. A command that describes a
*process* does not: a starting worker rejects every pending `shutdown` and
`steer_task` with `result_detail = "no engine was resident"`, rather than
stopping a service nobody asked to stop. `foreman engine` tells you which of
the two will happen when it queues the command.

### How fast a command lands

An idle engine wakes on `PRAGMA data_version`, and the insert commits from a
different connection, so a queued command wakes the engine within one tick
(0.5 s) rather than waiting out the poll interval. An engine that is mid-task
checks for commands, and for a user's Stop, before every workflow step, on
every `agent.tick` and every few seconds while a runner streams, and every two
seconds while tests run, so a Stop reaches an agent that has been working
quietly for twenty minutes.

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

**Foreman never changes which branch is checked out in your repository.**
Every task runs in its own git worktree that Foreman creates, owns, and
deletes.

If your checkout is on the default branch, each merge brings its files
along, as a fast-forward `git pull` would (ADR-0031). Your untracked files
and unstaged edits are kept. Where the update would overwrite one, or you
have staged changes, your checkout is left as it is, and the task's activity
says "The project's folder still shows an older main" with the reason. A
checkout on any other branch is never touched.

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
| developer, reviewers (native role steps) | the task's worktree |
| `_builtin:run_tests` | the task's worktree |
| refresh-before-develop, conflict-recovery merges | the task's worktree |
| `_builtin:merge` (`--no-ff` into the default branch) | the integration worktree |
| context projection | your `context_dir` **and** the worktree's own `.foreman/` |

### What your checkout sees

Never touched: your current branch, your index, your working-tree files, your
stash. Changed: **refs** — the default branch advances when a task merges, and
task branches appear and move. If you are sitting *on* the default branch when
a task merges, your files are brought to the merge as a fast-forward pull would
bring them (ADR-0031); where that would overwrite something of yours, they are
left as they were and the task's activity says why.

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

### How many tests ran

Foreman names an empty directory in `FOREMAN_TEST_REPORT_DIR` each time it
runs the tests. A `test_command` that writes JUnit XML reports there tells
Foreman how many tests ran, and the pages say "Passed · 1,599 tests"
(ADR-0035). A command that writes none still runs; the count is unknown.

```bash
# pytest
pytest --junitxml="$FOREMAN_TEST_REPORT_DIR/pytest.xml"
# vitest
npx vitest run --reporter=default --reporter=junit --outputFile.junit="$FOREMAN_TEST_REPORT_DIR/vitest.xml"
# unittest, with unittest-xml-reporting installed
python -m xmlrunner discover -s tests -o "$FOREMAN_TEST_REPORT_DIR"
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

#### The review sandbox

The code reviewer (`run_scope = "sandbox"`) runs as you, with Bash. It is kept
from your credentials, from other projects and from the network by **Claude
Code's own sandbox** (bubblewrap), which Foreman turns on for the step with
`claude --settings` (ADR new-claude-code-sandbox, amending ADR-0041 section 5).
Foreman builds no sandbox of its own.

What is enforced, and by what:

| What | How |
|---|---|
| The step never runs without its sandbox, and no command runs outside it | `failIfUnavailable` and `allowUnsandboxedCommands = false`; Foreman also checks for `bwrap` and `socat` first. A machine without them fails the step with the reason. |
| Commands write only in the step's own working copy and its own temporary directory | the sandbox's file system is read-only everywhere else. Each step gets a temporary directory of its own (`/tmp/foreman-sbx-…`, its `TMPDIR` and Claude Code's), removed with the sandbox; Claude Code's per-user directory `/tmp/claude-<uid>`, which every session of yours shares, is closed to it. A write into a closed directory may seem to work: it lands in a throwaway copy nothing outside sees. |
| Nothing in the branch under review configures the step | the clone is the step's working directory, so its `.claude/settings.json` is the branch's: Foreman loads no project settings (`--setting-sources user`) and turns every hook off (`disableAllHooks`). A hook, a status line or an `apiKeyHelper` runs outside the sandbox, as you; a branch could otherwise commit one. |
| The step does not reach the Claude Code session you started the engine from | the variables of that session (`CLAUDE_CODE_MESSAGING_*`, `CLAUDE_CODE_SESSION_*`, `CLAUDECODE`, …) are never given to an agent; with them, and unix sockets allowed, a command could talk to your interactive session. |
| Commands reach no host but the ones you list | the sandbox's proxy refuses every other host (`github.com`, a package index), whatever the command does with proxy variables. `localhost` works, so the project's dashboard preview can be served and fetched in one command. `sandbox_allowed_hosts` lists more. |
| Commands cannot read your home directory, or the directory the repository sits in (your other projects) | `denyRead` of both, with these opened inside: the step's working copy, the repository's `.git/objects`, what `worktree_link_paths` links in, and `sandbox_read_paths`. What is closed is invisible to a command (`No such file or directory`). |
| The Read, Grep and Glob tools read the same | the sandbox does not cover them; Foreman gives them permission rules that deny every entry of those directories except what is opened (a deny rule wins over an allow, so the entries are listed). |
| Commands do not see the backend's keys | `ANTHROPIC_*`, `OPENAI_*`, `CODEX_*` and `CLAUDE_CODE_OAUTH*` in the step's environment are masked from commands (`sandbox.credentials`). |
| Nothing the step does to git reaches your repository | the working copy is its **own clone** of the commit under review: objects shared, **no remote**, its own refs and config. A ref moved, a tag made or a config changed in it stays in it; a linked worktree would write your repository's refs. The task's branch is still checked after the step, put back if it moved, and the step fails. |

Codex (`run_scope` on `backend = "codex"`):

- `none`: the thread runs in Codex's `read-only` sandbox without network, with
  an approval policy that asks about every command (`untrusted`) and the
  shell tools switched off; Foreman declines each request.
- A role that is only not given Bash (a reviewer with Read, Grep and Glob):
  the same, but with the shell on, since Codex reads files through it. Codex
  runs the commands it trusts as read-only (`cat`, `ls`, `grep`) and asks
  about the rest, which Foreman declines.
- `sandbox`: Codex's sandbox cannot keep reads of your home directory, your
  credentials or other projects from a step, so **a `sandbox` role on Codex is
  refused when the role loads**. A role that accepts the open reads writes
  `accept_open_reads = true` under `[agent.flags]`: it then runs in Codex's
  `workspace-write` sandbox, in the clone, without network and without the
  host's `/tmp` and `$TMPDIR` (`exclude_slash_tmp`, `exclude_tmpdir_env_var`),
  and is never allowed out of it (approval policy `never`). Foreman reads back what the app
  server applied and refuses to run the step in another sandbox.
- Checked against codex-cli 0.159.3's app server for what it applies
  (`thread/start`); its enforcement of a command was not run live, as the
  engine's Codex login was refused (401) when this was written.

What the machine needs: Linux with `bubblewrap` (`bwrap`) and `socat` (Ubuntu:
`sudo apt install bubblewrap socat`), and Claude Code with sandbox support.

What a project sets, all host-level (`foreman config <project> --set`):

- `sandbox_allowed_hosts`: hosts the step may reach (default none).
- `sandbox_read_paths`: what the toolchain needs that lies under your home or
  beside the repository (a Python or Node you installed under `~`, a cache,
  and the base interpreter a `worktree_setup_command` venv points to). A
  reviewer that cannot start `python` or `node` is missing one.
- `sandbox_allow_unix_sockets`: needed for a browser (the screenshots script).
  Off, creating a unix socket is refused. On, Foreman closes `/run` and the
  temporary directories (where your session bus, container engine, ssh agent
  and X server have their sockets, and `/run/user/<uid>/cc-socks` your Claude
  Code sessions' messaging sockets); nothing under them is opened again but
  the step's own temporary directory. `/etc/resolv.conf` is a link into
  `/run` on many systems and disappears too: a name lookup that does not go
  through the proxy fails.
- `worktree_setup_command` builds the clone's environment, as for a task
  worktree, outside the sandbox and with network. Build a venv and
  `node_modules` of its own there; a path linked with `worktree_link_paths`
  is **read-only** to the step (a build that writes into a linked
  `node_modules` fails). The clone is given the repository's git identity
  (`user.name`, `user.email`), as your `~/.gitconfig` is closed to it.
- `sandbox_database_copy`: puts a copy of **this project's** records in the
  clone, at `.review/live.db`, for `scripts/review_screenshots.py` (which
  cannot read the main checkout). Off by default. The copy is made with
  SQLite's backup, then every other project's rows, the API tokens, the
  notification destinations and deliveries, the manager's conversations and
  the leases are taken out and the file is vacuumed. What is left (this
  project's tasks, runs, transcripts) is readable by the reviewer.

A server's admin login (Assay's `.env.admin`) or any other secret is **never
linked or listed in `sandbox_read_paths`**: whatever the step can read, it can
quote in its review.

Where it stops:

- **The developer step is not sandboxed.** It runs as you, in the task's
  worktree, with your credentials and the network. Sandboxing it is a separate
  task.
- Anything the reviewer is allowed to read is in its context, and so with the
  model provider. The backend's own keys are kept from commands, not from
  Claude Code itself.
- A host in `sandbox_allowed_hosts` is open to everything the step runs.
- A sandbox a killed engine left behind is removed when an engine starts for
  the project again.
- A service on your machine (a database on `localhost:5432`, a server on your
  LAN) is out of reach: `localhost` inside the sandbox is the sandbox's own,
  and a host in `sandbox_allowed_hosts` is reached only through the proxy,
  which a database driver does not use. Tests that need such a service must
  be skipped for the reviewer (for instance with a variable in its role's
  `[agent.env]`).

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

They are the project's records, not a task's: `for_task_id` names the task
that needed the room (ADR-0037).

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
| `rests_on` | no | documents of the repository the task rests on: a list of `"path"`, `"path#heading"` or `{"path", "heading"}`. A path that is not a file on the default branch refuses the request (400) with the reason; each is stored with the default branch's commit when it was named |
| `task_type` | no | defaults to `fix` (not `feature`: most work arriving from outside is a problem report) |
| `priority` | no | integer |
| `complexity` | no | Accepted and ignored: Foreman keeps no task size. A system that still sends it is not refused, and what it sends is not read (not even an unknown value) |
| `source` | no | `system`, `external_ref`, `url`, `reporter` — all strings |
| `sprint_id` | no | omit to file into the project's backlog |

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
the project's **backlog** (ADR-0021): one per project, id `<project>-backlog`,
created on first use. The backlog is not a sprint and the engine never runs
it; work there runs once a person plans it into a sprint (`foreman backlog
plan`, `POST /api/v1/projects/{id}/backlog/plan`). Databases that had an
intake queue sprint (`<project>-intake`) had its waiting work moved into the
backlog by migration 21.

**The `triage` policy decides the arriving status** (§14), resolved for the
task's type:

- `human` (the default) — the task lands in **`triage`**. The engine never
  selects a `triage` task, and one `engine.attention_needed` turn with trigger
  `triage` is raised so a person sees it. Accept it with `foreman backlog accept
  <task-id>` (or `foreman task accept`), `POST /api/v1/tasks/{id}/accept`, or
  the board's **Accept** button; decline it with `foreman backlog decline`.
- `auto` — the task lands accepted (`todo`) in the backlog with no person
  involved, and waits there until it is planned into a sprint.

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
| **400** | Missing `title`, an unknown `task_type`, or a malformed `source` |

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
| Your checkout suddenly shows a large uncommitted diff | You are sitting on the default branch, a task merged into it, and your checkout could not be brought along (the task's activity says "The project's folder still shows an older main" and why: usually staged changes). Commit or unstage them, then `git merge --ff-only main` or `git reset --hard main` if nothing of yours is in it. |
| Intake answers 401 with a token you just created | The dashboard's shared token was sent instead of the project API token — intake takes only the `fmn_…` secret from `foreman token create`. |
| Intake answers 403 | The token is live but belongs to another project (or lacks `intake`). `foreman token list <project>` shows which project's tokens exist. |
| A route other than intake answers 403 with "only valid on … /intake" | An `fmn_…` API token was sent to a dashboard route. Use the dashboard token there. |
| Intake keeps returning 200 and never creates a task | It is idempotent on `(system, external_ref)`: that pair was filed before. Send a new `external_ref`, or omit `source` to force a new task. |
| Intake tasks are filed but never run | They are in the backlog, which never runs. Accept them if they are filed, then plan them into a sprint: `foreman backlog plan <project> <task-id>... --sprint <sprint-id>`. |
| `.foreman/worktrees/` keeps growing | Trees of tasks that never reached `mark_done`. Lower `max_live_worktrees`, or run `foreman worktree prune <project>` (or Settings → Task working copies → Remove unused copies) to remove anything done, cancelled, or unclaimed. |

---

*Generated as part of the review-roadmap closeout. Keep this manual current when
CLI flags, settings, roles, workflows, or API endpoints change.*
