# ADR-0011: The Resident Engine And The Project Engine Lock

- Status: accepted
- Date: 2026-09-04
- Amended: 2026-09-04 — *The command table is the only control channel*

## Context

Until sprint 54 the engine's only autonomous entry point was `foreman run`,
which exits as soon as no runnable task remains. Anything that arrives
afterwards — a task typed into the CLI, a task created from the dashboard, a
task posted to the intake endpoint queued for later in this sprint — waits for
a person to press Run again. Phase 1 of
`docs/reviews/production-readiness-review.md` requires a worker that stays
resident so other systems can hand Foreman work.

Making the engine resident changes two things that were previously true by
accident:

1. **Concurrency became real.** A one-shot run was short and human-triggered,
   so two of them overlapping was unlikely. A resident engine is always
   running, so *every* `foreman run` and every dashboard Run press now overlaps
   it by default. The per-task lease does not solve this: it stops two engines
   from executing the *same* task, but nothing stops a second engine from
   selecting a *different* task and checking out its branch in the same working
   copy while the first engine's agent is editing files there.
2. **The operator surface disappeared.** A one-shot run prints a summary to a
   terminal a person is watching. A resident worker has no terminal.

## Decision

### One engine per project, enforced by an engine lease

A Foreman engine must hold a lease with `resource_type="engine"` and
`resource_id=<project id>` for the whole time it may touch the project. This
covers `foreman serve` and `foreman run` alike, so neither can start while the
other is resident. A refused acquisition is a clean non-zero exit that names
the current holder; it never modifies a task.

The lock is a row in the existing `leases` table rather than a lock file or a
new table. That table already supports arbitrary resource types, so this needs
**no migration**; the lock is visible to the same lease inspection and recovery
paths as every other lease; and a crashed engine releases its lock by lease
expiry rather than leaving a stale file that a human must delete.

The engine lease duration is 120 seconds — shorter than the 300-second per-task
default. The trade is explicit: a SIGKILLed engine blocks its project for at
most that long, and no correctness property depends on the window because the
per-task lease still guards the task itself.

The lock is scoped per project, not per repository or per machine. Two projects
in two checkouts are independent and must be able to run at the same time.

### The lock heartbeats on a timer thread, not on agent output

The per-task lease is renewed from the runner's event stream — every tick of
agent output heartbeats it. That is right for a task lease: an agent that has
died deserves to lose its task.

It is wrong for the engine lock. An agent can legitimately be silent for many
minutes, and an engine that lost its *project* because its *agent* went quiet
would hand the whole checkout to a second engine while the first is still
editing files in it. So the engine lock is renewed from a dedicated daemon
thread on wall-clock time (every 20 seconds, six renewals per lease),
independent of what the engine is doing.

That thread opens its **own** `ForemanStore`. A SQLite connection must not be
shared across threads, and the main thread's connection is busy inside
orchestration for the whole time the heartbeat needs to write.

A refused renewal means another engine now owns the project. The engine stops:
agent process groups are terminated and the main thread is interrupted, which
routes into the orchestrator's existing guarded-step path — the active run is
settled as `killed` and the task stays resumable at its persisted step, exactly
as a shutdown signal behaves. The process then exits non-zero, because losing a
lock is a failure while a requested stop is not.

### Per-task leases stay as they are

The engine lock does not replace the per-task lease and does not change its
semantics. The two answer different questions: the engine lock answers "may
this process touch this project's checkout at all", the task lease answers
"which task is mine". Keeping both means the day parallel workers land — each
holding a task lease under a shared or per-worktree engine scope — the task
lease is already in place and already tested. Collapsing them now would have to
be undone then.

### An idle engine wakes on `data_version`, not on a table scan

An idle pass waits until either `PRAGMA data_version` changes or the poll
interval (default 5 s) elapses. `data_version` moves only when a *different*
connection commits, so it detects work queued by the dashboard, the CLI, or the
intake API without querying any table, and an idle engine's only activity
between wakes is that one pragma read.

The lock heartbeat is itself a different connection, so it bumps
`data_version` on its own timer. This is why retention pruning and crash
recovery run **once at startup and after a pass that executed work**, never on
an idle wake: otherwise every heartbeat would trigger a full maintenance sweep
and idle would become a busy loop. `run_project(maintenance=...)` makes that
explicit rather than implicit.

### A failed task is isolated, not fatal

An exception while running one task marks that task `blocked` with the error as
its `blocked_reason`, records a system run, and emits `engine.attention_needed`
through the same path a workflow block takes, so the supervision digest and the
attention trigger keep working unchanged. The service then backs off (5 s,
doubling per consecutive failure, capped at 5 minutes, reset after a clean
pass) and continues.

`run_project` raises `TaskExecutionError`, which carries the task id, so the
loop knows what to block instead of inferring it. Errors that are *not*
task-scoped (an unknown project, an invalid task-selection mode) still end the
service: they will not fix themselves, and retrying forever would hide them.

### The process log is the operator surface

`foreman/logs.py` emits one JSON object per line on stderr with `ts`, `level`,
`event`, and the identity fields (`project_id`, `task_id`, `run_id`, `step`)
whenever they are known. `foreman serve` logs its lifecycle
(`serve.started`, `serve.lock_acquired`, `serve.lock_busy`,
`serve.pass_completed`, `serve.idle`, `serve.task_failed`, `serve.lock_lost`,
`serve.stopping`, `serve.stopped`) and never prints — including the refusal
path, so a supervisor reading only the log can tell a busy lock from a crash.
The orchestrator mirrors every persisted event to the same logger, so the
process log alone tells the story of a run without a database query. Logging
stays inert until the CLI configures it, so importing Foreman as a library
emits nothing.

Mirroring is levelled by event family, and the mapping lives in
`foreman.logs.event_log_level` rather than at the call site so it is testable
on its own. The narrative — `engine.*`, `workflow.*`, `gate.*`, `signal.*`, and
the agent *step* lifecycle — is INFO. The agent *output* firehose
(`agent.raw_output`, `agent.prompt`, `agent.tool_use`, `agent.tool_result`,
`agent.cost_update`, `agent.tick`) is DEBUG: it arrives several times per
second, and a resident engine whose own lifecycle is buried in agent chatter
has no usable operator surface. Persistence is unaffected — every event is
still written to the database in full, so the log level is a reading choice,
not a retention one. Unrecognized event types default to DEBUG, because a new
event type is more likely to be a new stream than a new decision, and the four
narrative families are prefix-matched so a genuinely new decision event reaches
INFO with no code change.

## Amendment (2026-09-04): the command table is the only control channel

The original decision left a resident engine reachable only by signal. That is
not enough, and the gap is not cosmetic:

- a signal cannot carry an argument, so it can never say "run *that* task";
- a signal cannot be queued for an engine that is not up yet;
- a signal leaves no record of who sent it or what came of it;
- a signal cannot be sent at all by a dashboard on another host, or by an
  intake API sharing only the database.

### Decision

`engine_commands` (migration 15) is the **only** control channel to a resident
engine. Every actor that wants to steer one — the CLI, the dashboard, the
intake API — inserts a row and reads the outcome back from the same row.
Nothing may reach into a resident engine any other way: no process handles kept
in a module-level dict, no `kill` against a pid the caller happened to
remember, no second `foreman run` racing the resident worker for the lock.

The vocabulary is `pause`, `resume`, `run_task`, `stop_task`, `shutdown`, and
the lifecycle is `pending` → `acknowledged` → `completed` | `rejected`, always
with a `result_detail`. The row *is* the audit trail; `requested_by` is never
blank.

**Why a table rather than a socket or a pipe.** The database is already the
thing every actor shares — that is the product's premise — and it is already
how an idle engine learns that anything happened (`PRAGMA data_version`). A
socket would need a second transport, a second auth story, a second liveness
problem, and would not survive the engine being down; a command queued for an
engine that starts in ten minutes is a feature, not an edge case. The table
also gives durability and history for free, which a socket cannot.

**Why the engine polls rather than being interrupted.** A command must be able
to stop an agent step that has been running for an hour, and the only place the
engine reliably regains control during such a step is the runner's event
stream. So the orchestrator takes a `command_poll` callback and calls it before
every workflow step and on every `agent.tick` — the same heartbeat that already
keeps the task lease alive. The poll site sits immediately *after* the resume
point is persisted, so an interrupt always leaves the task resumable at the
step it was about to run rather than the one it just finished.

An interrupting command raises `EngineCommandInterrupt`, a `BaseException` for
the same reason `EngineShutdown` is one: the orchestrator's defensive
`except Exception` fallbacks turn an exception into a failed agent outcome, and
an operator's `pause` is not an agent failure. It settles through the existing
`_abandon_run` path, so a commanded stop and a signalled stop leave identical
state behind — run `killed`, task resumable — and there is one settlement path
to reason about rather than two.

### A paused engine, and a stopped task

`pause` is about the engine, not the work: it stops new work being picked up
and stops the running step, but changes **no task status**, keeps the lock, and
keeps heartbeating it. A paused engine still answers `resume` and `shutdown`,
because an engine that could be paused into unreachability would be a worse
operator surface than no pause at all.

`stop_task` is about the work: the task becomes `blocked` with
`blocked_reason = "Stopped by <requested_by>"`. No new task status was
introduced. `blocked` already means exactly what a stopped task needs it to
mean — not runnable until a human or the manager says otherwise — and every
surface that already reports blocked tasks reports stopped ones for free. A
stop records no `engine.attention_needed`: a person who pressed Stop does not
need to be told they stopped something. The dead-letter reporting slice is what
makes a forgotten `blocked` task visible, and it does not care why the task was
blocked.

### Commands addressed to an engine that is gone

A command that describes *work* outlives the process; a command that describes
a *process* does not. So a starting engine honours a pending `resume` or
`run_task` and rejects every pending `pause`, `stop_task`, and `shutdown` with
`result_detail = "no engine was resident"`. The alternative — applying them —
would let a `pause` queued against yesterday's engine silently pause today's,
which is the kind of failure nobody thinks to look for.

### Consequences of the amendment

- The dashboard's Run/Stop buttons and `_RUNNING_PROCS` are now the only thing
  that talks to an engine outside this channel, and are scheduled for
  replacement in the next slice. Until then a dashboard Run still competes for
  the engine lock and is refused while a `serve` is up.
- Rejections are ordinary outcomes, not errors. A caller must read the command
  row back to learn what happened; printing the command id from the CLI is what
  makes that possible.
- The poll adds one indexed single-row read per workflow step and per agent
  tick. Ticks are seconds apart at worst, so the cost is negligible against an
  agent step, and an idle engine still reads nothing but `data_version`.

## Consequences

- A `foreman run` — including the one the dashboard's Run button spawns — now
  fails with a clear message while a resident engine is up. That is the
  intended behaviour; the command table added in the amendment above is what
  the dashboard writes to instead of spawning a competing process.
- After an engine is SIGKILLed, its project is unavailable for up to 120
  seconds. Recovering faster would need liveness beyond lease expiry (a pid or
  a host check), which is deferred until it is actually needed.
- Blocking a task on a failure is a policy choice: a transient failure (a
  network blip during a merge) parks a task that a human or the manager must
  unblock. The alternative, silent retry, risks a task looping forever. The
  dead-letter reporting slice makes those blocks visible.
- `EngineLock` is a general lease-backed context manager. When parallel workers
  arrive it is the natural place for a worker-scoped resource id.

## Alternatives considered

- **A lock file in the repository.** Rejected: stale files survive a crash and
  need manual cleanup, they are invisible to the dashboard and to lease
  inspection, and they do not work when the database is shared across
  checkouts.
- **Renewing the engine lock from the agent event stream.** Rejected: it makes
  a silent agent cost the engine its whole project.
- **Reusing the per-task lease as the engine lock.** Rejected: it conflates two
  different questions and would have to be unpicked for parallel workers.
- **Polling tables on a fixed interval instead of `data_version`.** Rejected:
  it makes an idle engine's cost proportional to project size for no benefit.
