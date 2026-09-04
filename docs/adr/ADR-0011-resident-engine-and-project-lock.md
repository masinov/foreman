# ADR-0011: The Resident Engine And The Project Engine Lock

- Status: accepted
- Date: 2026-09-04

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

## Consequences

- A `foreman run` — including the one the dashboard's Run button spawns — now
  fails with a clear message while a resident engine is up. That is the
  intended behaviour, and the next slice gives the dashboard a command table to
  write to instead of spawning a competing process.
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
