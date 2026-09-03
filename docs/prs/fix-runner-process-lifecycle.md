# PR Summary: fix/runner-process-lifecycle

## Summary

Sprint 53, slice 2. Makes the agent process layer safe for unattended
operation. Before this slice a silent agent could hang the engine forever, a
stopped or crashed engine left the agent and everything it spawned running,
a chatty child could deadlock on a full stderr pipe, output decoding depended
on the host locale, the test built-in had no timeout, and a shutdown left the
run row `running` with the checkout on the task branch.

## Scope

- **`foreman/runner/process.py`** (new): `ManagedProcess` reads stdout on a
  pump thread and yields `None` ticks while the child is silent, drains
  stderr continuously into a bounded buffer, starts children in their own
  session, and terminates or kills the whole process group with a grace
  period. A module registry tracks live children; `install_shutdown_handlers`
  installs SIGTERM and SIGINT handlers that terminate every registered group
  and raise `EngineShutdown` in the main thread, plus an atexit drain.
  `popen_kwargs` standardizes pipes, UTF-8 with replacement, line buffering,
  and `start_new_session`.
- **Claude Code runner**: rebuilt on `ManagedProcess`. Time and cost gates
  are evaluated on every silent tick as well as on every parsed event; each
  tick yields an `agent.tick`. The child is always closed in a `finally`, so
  an abandoned generator (the orchestrator raised) terminates the agent's
  process group.
- **Codex runner**: `_JsonRpcClient` reads through `ManagedProcess`; the
  startup handshake and every request are bounded by a wall-clock
  (`startup_timeout_seconds`, default 60 s) instead of blocking forever;
  silent turns tick and enforce the time gate; kill and close reach the
  process group.
- **Orchestrator**: `agent.tick` events heartbeat the task lease and are never
  persisted. `_renew_task_lease` now raises `LeaseLostError` when the store
  refuses the renewal. `_execute_agent_step_guarded` settles the run row on
  interruption: `EngineShutdown` or `KeyboardInterrupt` records an
  `agent.killed` event with `gate_type="shutdown"`, marks the run `killed`,
  releases the lease, and re-raises with the task left `in_progress` at its
  persisted resume point; a lost lease does the same with
  `gate_type="lease_lost"` but leaves the task and lease to the new holder.
- **Test built-in**: `test_timeout_seconds` (default 1800, 0 disables) bounds
  `_builtin:run_tests`; the command runs in its own process group,
  registered for shutdown, and a timeout kills the group and returns
  `failure` with a `timed_out` flag on the `engine.test_run` event.
- **CLI**: `foreman run` installs the shutdown handlers and exits 130 with a
  clear message when interrupted.
- **Settings**: `ProjectSettings.test_timeout_seconds`.

## Files changed

- `foreman/runner/process.py` (new), `foreman/runner/__init__.py`,
  `foreman/runner/claude_code.py`, `foreman/runner/codex.py`,
  `foreman/orchestrator.py`, `foreman/builtins.py`, `foreman/settings.py`,
  `foreman/cli.py`
- `tests/test_runner_lifecycle.py` (new, 15 tests)
- `docs/sprints/current.md`, `docs/STATUS.md`, `docs/MANUAL.md`,
  `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `CHANGELOG.md`

## Migrations

- None.

## Risks

- **Behavior change:** `foreman run` now handles SIGINT itself. Ctrl+C
  terminates the agent group, settles the run, and exits 130 instead of
  printing a traceback.
- Process-group signalling requires `start_new_session`; a child spawned
  through a custom `popen_factory` without it is signalled individually,
  never through the engine's own group (the wrapper checks the child leads
  its own group before using `killpg`).
- Ticks default to 15 s, so a hung agent is detected within one tick of its
  time limit; the lease heartbeat interval (30 s) is now honored even when
  the agent is silent.
- The Codex startup timeout is a new failure mode for slow hosts; it surfaces
  as a preflight-style `InfrastructureError` naming the request.

## Tests

- `./venv/bin/python -m unittest discover -s tests` — 620 passing (was 605;
  +15 in `tests/test_runner_lifecycle.py`, which use real subprocesses for
  ticks, stderr floods, process-group kills, and the SIGTERM handler).
- `scripts/validate_repo_memory.py` clean; `git diff --check` clean.

## Acceptance criteria satisfied

- a silent agent hits its time limit and is killed without any output,
- a stderr flood of 300 KB completes instead of deadlocking,
- an abandoned run kills the grandchild the agent spawned,
- SIGTERM to the engine terminates registered children and raises in the
  main thread,
- a shutdown mid-step leaves the run `killed`, the task resumable, the lease
  released, and the checkout on the default branch,
- a lost lease stops the engine without touching the task or the new lease,
- the test built-in times out and kills its process group.

## Follow-ups

- Sprint 53 slices 3–6.
- Phase 1: session-aware infrastructure retry; a project-level engine lock
  with a timer-thread heartbeat replacing per-task leases; structured logging
  of shutdown and lease-loss events.
