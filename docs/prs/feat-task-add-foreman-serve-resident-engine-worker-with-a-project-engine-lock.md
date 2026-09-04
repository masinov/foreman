# PR Summary: feat/task-add-foreman-serve-resident-engine-worker-with-a-project-engine-lock

## Summary

- Adds `foreman serve <project-id> [--poll-seconds N] [--once]`: the same
  engine as `foreman run`, kept resident. Each pass calls
  `ForemanOrchestrator.run_project` once; a pass that executed nothing waits
  until either `PRAGMA data_version` changes or `--poll-seconds` (default 5)
  elapses, then runs again. Work queued by the CLI, the dashboard, or a future
  intake API is picked up without a person pressing Run.
- Adds a reusable project **engine lock** (`foreman/engine_lock.py`): a lease
  with `resource_type="engine"` and `resource_id=<project id>`, held for the
  whole session by both `foreman serve` and `foreman run`. A second engine
  exits non-zero naming the holder and touches no task. Renewal runs on a
  daemon timer thread with its own `ForemanStore` connection, so a silent agent
  never costs the engine its project.
- Adds JSON-lines process logging (`foreman/logs.py`). `serve` never prints;
  its lifecycle and every event the orchestrator persists go to stderr as one
  JSON object per line, so the process log alone tells the story of a run.
- Failure isolation: a task whose execution raises is blocked with the error as
  its `blocked_reason` plus an `engine.attention_needed` turn, and the service
  continues after a doubling backoff. A stop (SIGTERM/SIGINT) settles the
  active run as `killed`, keeps the task resumable, releases the lock, and
  exits 0.

## Scope

In scope: the resident worker, the engine lock, structured logs, the
orchestrator seams they need, tests, and docs.

Out of scope (the next task): the engine command table, dashboard wiring, and
dead-letter reporting. The dashboard still spawns a `foreman run` subprocess;
it now competes for the engine lock instead of cooperating with a resident
worker, which is exactly what the command table replaces.

## Files changed

New:

- `foreman/serve.py` — `ResidentEngine` (the loop), `serve_project()`,
  `ServeResult`.
- `foreman/engine_lock.py` — `EngineLock`, `EngineBusyError`,
  `EngineLockLostError`, `stop_engine_on_lock_loss`.
- `foreman/logs.py` — `JsonLinesFormatter`, `configure_json_logging`,
  `log_event`, `compact_payload`.
- `tests/test_serve.py` — 34 tests.
- `docs/adr/ADR-0011-resident-engine-and-project-lock.md`.

Changed:

- `foreman/orchestrator.py` — `run_project(maintenance=...)`;
  `TaskExecutionError` (carries the task id); `_run_task_isolated()`;
  public `block_task_for_error()`; `_emit_event()` mirrors to the process log.
- `foreman/cli.py` — `serve` subcommand and a thin `handle_serve`; `run` takes
  the engine lock and gains `--json-logs`.
- `tests/test_cli.py` — serve wiring, lock refusal, lock release, and a
  resident engine picking up a task queued by another process.
- `docs/MANUAL.md` (new §6.1 and a rewritten §22), `README.md`,
  `docs/ARCHITECTURE.md`, `docs/adr/README.md`, `CHANGELOG.md`,
  `docs/STATUS.md`, `docs/sprints/current.md`.

## Migrations

- none. The `leases` table already supports arbitrary resource types, so the
  engine lock reuses it as-is. No new task status and no new columns.

## Risks

- **The dashboard's Run button now competes for the lock.** While a `serve` is
  resident, pressing Run fails with the busy message instead of starting a
  second engine. That is the intended safety property, but it is a visible
  behaviour change until the command-table slice lands. Existing dashboard
  tests pass unchanged.
- **A `kill -9`'d engine holds its project for up to 120 s** (the engine lease
  duration) before the lock expires. Deliberate: shortening it further trades
  against renewal margin, and no correctness property depends on the window
  because the per-task lease still guards the task.
- **Lock loss interrupts the main thread.** When a renewal is refused, the
  heartbeat thread terminates agent process groups and raises into the main
  thread, which routes through the orchestrator's existing guarded-step path
  (run settled `killed`, task resumable). The blunt instrument is deliberate:
  the main thread can be blocked inside a long agent step, and finishing that
  step while another engine owns the project is worse.
- **Blocking a failed task is a policy choice.** A transient failure parks a
  task that a human or the manager must unblock, rather than retrying silently
  and risking a task that loops forever. Dead-letter reporting is queued next.

## Tests

```
./venv/bin/python -m unittest discover -s tests    # 645 tests, OK
./venv/bin/python scripts/validate_repo_memory.py  # OK
```

`tests/test_serve.py` (34 tests) covers: lock refusal naming the holder,
reacquisition after release, takeover after expiry, heartbeat renewal on its
own connection, a refused renewal marking the lock lost, a lost lock not
stealing its successor on release, release on an unhandled error, `--once`,
maintenance gating (startup and after work, never on idle wakes), an idle
engine polling nothing but `data_version`, the immediate wake when another
connection commits, failure isolation with a doubling and resetting backoff,
the backoff cap, a shutdown mid agent step that settles the run as `killed` and
releases the lock, and the JSON formatter (field order, omitted unknown fields,
truncation, unserializable values, idempotent configuration, event mirroring).

`tests/test_cli.py` adds five: `run` refused under a resident engine, `run`
releasing the lock so a second run succeeds, `serve --once` logging JSON lines
and releasing the lock, `serve` refused under a held lock, a rejected
`--poll-seconds 0`, and a subprocess `serve` parked on a 120 s poll that picks
up a task queued by the test process. No test invokes a real `claude` or
`codex` binary.

## Screenshots or output examples

```
$ foreman serve foreman --once
{"ts":"2026-09-04T11:52:36.931Z","level":"INFO","event":"serve.lock_acquired","project_id":"foreman","holder_id":"5e29e543-…","expires_at":"2026-09-04T11:54:36.931339Z","lease_id":"lease-087fc41d0f20"}
{"ts":"2026-09-04T11:52:36.931Z","level":"INFO","event":"serve.started","project_id":"foreman","holder_id":"5e29e543-…","once":true,"poll_seconds":5.0}
{"ts":"2026-09-04T11:52:36.932Z","level":"INFO","event":"serve.pass_completed","project_id":"foreman","blocked_task_ids":[],"executed_task_ids":[],"stop_reason":"idle"}
{"ts":"2026-09-04T11:52:36.932Z","level":"INFO","event":"serve.stopped","project_id":"foreman","executed_task_ids":[],"exit_code":0,"passes":1,"stop_reason":"once"}

$ foreman run foreman          # while the above is resident
Another Foreman engine is already running project 'foreman' (lock holder
5e29e543-…, lease expires 2026-09-04T11:54:36Z). Stop it, or wait for its
lease to expire, before starting another.
$ echo $?
1
```

## Acceptance criteria satisfied

- `serve --once` runs one pass and exits 0; a resident `serve` picks up a task
  added from another process (covered by
  `test_serve_picks_up_a_task_queued_by_another_process`, which parks the
  engine on a 120 s poll so only the `data_version` wake can explain it).
- A second `serve` or a `run` exits non-zero naming the holder; the lock is
  reacquirable after release or expiry.
- The lock is renewed by a timer thread on its own connection and released on
  normal exit, `--once`, SIGTERM/SIGINT, and an unhandled error.
- A failing task is blocked with the error as `blocked_reason` and an
  `engine.attention_needed` event; the service continues after a doubling
  backoff that resets after success.
- SIGTERM during an agent step settles the run as `killed`, keeps the task
  resumable at its persisted step, terminates process groups, releases the
  lock, and exits 0. `foreman run` keeps exit code 130.
- Retention pruning and crash recovery do not run on idle wakes.
- `foreman/logs.py` emits one JSON object per line on stderr with `ts`,
  `level`, `event`, `project_id`; engine events are mirrored to it.
- Full suite and `scripts/validate_repo_memory.py` pass.
- `docs/MANUAL.md`, `README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`,
  ADR-0011, and this note are updated.

## Follow-ups

- **Next task (sprint 54 slice 2):** the engine command table. The dashboard
  and CLI should write commands the resident engine consumes instead of
  spawning a competing `foreman run`; the API should report the resident
  engine; and tasks the engine dead-lettered into `blocked` need reporting.
- A `--lease-seconds` / `--heartbeat-seconds` escape hatch for operators whose
  database is slow enough that the 120 s / 20 s defaults are tight. Not added
  now: no evidence it is needed, and every knob is a support surface.
- Faster recovery from a `kill -9`'d engine would need liveness beyond lease
  expiry (a pid or host check on the lease row). Deferred until it hurts.
