# PR Summary: feat/task-add-the-engine-command-table-and-foreman-engine-cli

## Summary

- `foreman serve` kept the engine resident, but nothing could talk to it except
  signals — and a signal cannot say "run *that* task", cannot be queued for an
  engine that is not up yet, and leaves no record of who sent it. This branch
  adds `engine_commands`, the durable control channel a resident engine
  consumes, and the `foreman engine` CLI that writes to it.
- Migration 15 adds the table; `ForemanStore` gains the enqueue/read/settle
  methods plus `get_engine_lock()`, a **token-free** view of the engine lease so
  operator surfaces can see who holds a project without the secret that would
  let them release it.
- The resident engine drains pending commands before every pass and gives the
  orchestrator a `command_poll` callback, called before every workflow step and
  on every `agent.tick`, so a `pause` reaches an agent that has been working
  quietly for twenty minutes.
- ADR-0011 is amended to record the command table as the **only** control
  channel to a resident engine.

## Scope

In scope: schema, store, orchestrator seam, resident-engine consumption, CLI,
tests, docs.

Out of scope (next task): rewiring the dashboard's Run/Stop buttons onto the
command table and adding the engine status view to the API. The dashboard is
untouched here and `_RUNNING_PROCS` is deliberately left in place; its tests
still pass unchanged.

## Files changed

- `foreman/migrations.py` — migration 15, `engine_commands` + its index.
- `foreman/models.py` — `EngineCommand`, `EngineLockView`, the command and
  status vocabularies, and `ENGINE_COMMANDS_NEEDING_A_RESIDENT_ENGINE`.
- `foreman/store.py` — `enqueue_engine_command`, `get_engine_command`,
  `list_engine_commands`, `next_pending_engine_command`, `mark_engine_command`,
  `get_engine_lock`; `ENGINE_RESOURCE_TYPE` moved here so the store and
  `engine_lock.py` cannot drift (the lock module now imports it).
- `foreman/errors.py` — `EngineCommandInterrupt`.
- `foreman/orchestrator.py` — the `command_poll` seam and its two call sites;
  `_execute_agent_step_guarded` settles a command interrupt as `killed` with
  `gate_type="command"`; new `stop_task()`, `release_task()`, and
  `record_engine_event()`.
- `foreman/serve.py` — the command state machine: startup rejection, the
  per-pass drain, the paused state, the interrupt settlement.
- `foreman/cli.py` — the `foreman engine` command group.
- `tests/test_engine_commands.py` (new), `tests/test_serve.py`,
  `tests/test_cli.py`, `tests/test_store_safety.py`.
- `docs/MANUAL.md`, `README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`,
  `docs/adr/ADR-0011-resident-engine-and-project-lock.md`, this note.

## Migrations

- **15 — `engine_commands`.** Columns: `id`, `project_id` (FK → `projects`,
  `ON DELETE CASCADE`), `command` (CHECK: `pause`, `resume`, `run_task`,
  `stop_task`, `shutdown`), `task_id` (nullable FK → `tasks`,
  `ON DELETE CASCADE`), `requested_by`, `requested_at`, `status` (CHECK:
  `pending`, `acknowledged`, `completed`, `rejected`), `acknowledged_at`,
  `completed_at`, `result_detail`. Index
  `idx_engine_commands_project_status` on `(project_id, status, requested_at)`.
- Purely additive — no table rebuild, no `RETURNING`, no `DROP COLUMN`, so it is
  within the bundled SQLite 3.31 limits and applies cleanly to a live database.
  Tested against a database created at version 14.

## Risks

- **Interrupting a workflow mid-flight.** Mitigated by polling only *after* the
  resume point is persisted, so an interrupt always leaves the task resumable at
  the step it was about to run, and by reusing the existing `_abandon_run` path
  so a commanded stop and a signalled stop leave identical state behind.
- **`EngineCommandInterrupt` escaping into the wrong handler.** It is a
  `BaseException`, so the orchestrator's `except Exception` fallbacks cannot
  swallow it into a "failed agent step". Covered by a test whose fake runner
  raises a `BaseException` if the poll never fires, so a silently ignored
  command fails the suite loudly rather than passing quietly.
- **Poll cost.** One indexed single-row read per workflow step and per agent
  tick. Ticks are seconds apart at worst; an idle engine still reads nothing but
  `PRAGMA data_version`.
- **A bad `run_task` ending the service.** A targeted pass that raises
  `OrchestratorError` now isolates that one task instead of ending the loop.
  Handler ordering matters here — `TaskExecutionError` and `LeaseLostError` both
  subclass `OrchestratorError` and are caught first.

## Tests

`./venv/bin/python -m unittest discover -s tests` → **724 tests, OK** (1 skip:
`test_e2e` needs pytest, pre-existing).

- `tests/test_engine_commands.py` (new, 25 tests): migration 15 columns,
  nullability, index columns, both `ON DELETE CASCADE` rules, both CHECK
  vocabularies, and that the SQL constraint and the Python tuples cannot drift;
  a database at version 14 upgraded to 15; store round-trip, ordering,
  filtering, limits, lifecycle stamps, and cascade-on-task-delete; the lock view
  including that it carries no lease token.
- `tests/test_serve.py`: startup rejection of stale `pause`/`stop_task`/
  `shutdown` and survival of pending `resume`/`run_task`; each command's
  semantics against an idle engine; a paused engine keeps its lock and still
  answers `shutdown`; a queued command wakes an idle engine at 1.0 s rather than
  the 60 s poll deadline (proving the `data_version` wait sees another
  connection's insert); and `pause`/`stop_task`/`shutdown` against a *running*
  agent step driven by a fake runner that blocks on `agent.tick` and queues its
  command from a second connection.
- `tests/test_cli.py`: every verb, the `--by` default, refusal paths, the status
  view (including that it never prints the lease token), and an end-to-end
  queue-then-`serve --once` round trip.
- `tests/test_store_safety.py`: unpinned from "14 is the latest migration" so
  the next migration does not break a test about the v14 rebuild.
- No test launches a real `claude` or `codex` binary.

`./venv/bin/python scripts/validate_repo_memory.py` → passes.

## Screenshots or output examples

```console
$ foreman engine stop-task foreman task-49 --by carla
Queued engine command: stop_task
Database: /src/foreman/.foreman.db
Project: foreman | Foreman
Command id: cmd-9f1c2a7b41e0
Requested by: carla
Task: task-49
Resident engine: 5e29e543-0e1c-4a6f-9a9e-1c2f1b6d40aa

$ foreman engine status foreman
Engine status
Database: /src/foreman/.foreman.db
Project: foreman | Foreman
Resident engine: 5e29e543-0e1c-4a6f-9a9e-1c2f1b6d40aa
State: running
Heartbeat: 6s ago (at 2026-09-04T12:31:02.114Z)
Acquired: 2026-09-04T12:14:31.882Z | Lease expires: 2026-09-04T12:33:02.114Z
Current task: none
Recent commands (1):
- [completed] stop_task | id=cmd-9f1c2a7b41e0 | task=task-49 | by=carla | at=2026-09-04T12:31:08.402Z
    Stopped task 'task-49': the agent process group was terminated, its run
    settled as killed, and the task is blocked (Stopped by carla).
```

A stale command rejected at startup, from the engine's own JSON log:

```json
{"ts":"2026-09-04T17:44:59.167Z","level":"WARNING","event":"serve.command_rejected","project_id":"p1","command":"pause","command_id":"cmd-4b0761d69177","detail":"no engine was resident","requested_by":"alice"}
```

## Acceptance criteria satisfied

- Migration 15 creates `engine_commands` with the stated columns, constraints,
  and index, applies cleanly to a database at version 14, and `foreman db
  version` reports 15. ✅
- `ForemanStore` round-trips engine commands and exposes a token-free engine
  lock view. ✅
- A resident `foreman serve` acknowledges and completes `pause`, `resume`,
  `run_task`, `stop_task`, and `shutdown`, records `engine.command_applied` /
  `engine.command_rejected`, and rejects stale
  `pause`/`stop_task`/`shutdown` at startup. ✅
- `pause` and `stop_task` during a running agent step terminate the agent
  process group and settle the run as `killed`; `pause` leaves the task
  resumable, `stop_task` blocks it with the requester in the reason. ✅
- Enqueuing from another process wakes an idle engine within the poll
  interval. ✅
- `foreman engine status|pause|resume|shutdown|run-task|stop-task` work as
  described and print the command id. ✅
- Full suite and `scripts/validate_repo_memory.py` pass. ✅
- `docs/MANUAL.md` (new §23 plus the CLI reference, log events, event taxonomy,
  and migration table), `README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`, the
  ADR-0011 amendment, and this note are updated. ✅

## Follow-ups

- **Next sprint task (already queued):** rewire the dashboard's Run and Stop
  buttons onto `engine_commands`, add the engine status view to the API, remove
  `_RUNNING_PROCS`, and report dead-lettered tasks.
- `foreman engine status` infers "paused" by scanning back through completed
  commands for the last `pause`/`resume`. That is correct and cheap, but the
  engine's paused state is not itself persisted; if a future surface needs it
  authoritatively (a supervisor deciding whether to restart, say), a
  `serve`-owned state row would be the honest fix.
- Commands are consumed by whichever engine holds the project lock. When
  parallel workers land, `run_task` will need a worker-scoped target rather than
  a project-scoped one.
