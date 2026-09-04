# PR Summary: feat/task-rewire-the-dashboard-onto-the-resident-engine-and-report-dead-letter-tasks

## Summary

- The dashboard stops managing processes. Run enqueues `resume` (plus
  `run_task` for a task-scoped start), Pause enqueues `pause`, and a task Stop
  enqueues `stop_task`; whichever `foreman serve` holds the project engine lock
  acts on them. `_RUNNING_PROCS`, `_agent_running`, and
  `_terminate_registered_agent` are gone.
- New `GET /api/projects/{id}/agent/status` reports `resident`, `holder_id`,
  `heartbeat_age_seconds`, `paused`, `current_task`, and the last ten commands;
  new `GET /api/projects/{id}/engine/commands` lists the log.
- With no engine resident there is nobody to send `resume` to, so the service
  spawns a detached `foreman serve <project> --db <path>` (stdout and stderr
  appended to `.foreman/serve.log`) through an injectable `ServeSpawner`. That
  is the single-machine bootstrap and the only process the dashboard starts; it
  keeps no handle on it.
- Blocked tasks now say *which kind* of blocked: `gate` (parked at a
  `_builtin:human_gate` step, resolved by Approve/Deny) or `engine` (the
  engine's dead letter — loop limit, unhandled outcome, cost or time gate,
  branch violation, failure isolation, `stop_task`). Derived from the workflow
  definition; no migration, no new status.

## Scope

In scope: the dashboard service and API surface for engine control, the shared
read-side derivations, dead-letter reporting across the API and the CLI, the
frontend header and task board, docs, and the ADR-0002 amendment.

Out of scope: the intake endpoint and API tokens (slice 3), the policy matrix
(slice 4), and any change to how the engine itself applies a command.

## Files changed

- `foreman/engine_control.py` (new) — the read-side derivations the CLI and the
  dashboard share: `describe_engine()` (residency, heartbeat age, lease expiry,
  paused, current task, recent commands), `engine_is_paused()`,
  `resolve_gate_steps()` / `blocked_kind()` / `blocked_kind_counts()`,
  `default_command_requester()`, and the `spawn_serve()` bootstrap with its
  `ServeSpawner` seam.
- `foreman/dashboard_service.py` — process registry removed; `start_agent`,
  `stop_agent`, `stop_task` enqueue commands; new `agent_status` and
  `list_engine_commands`; `blocked_kind` on task payloads and
  `blocked_gate`/`blocked_engine` on project payloads; `serve_spawner` injected
  through the constructor.
- `foreman/dashboard_backend.py` — `GET .../agent/status`, `GET
  .../engine/commands`, and `requested_by` on the start/stop/task-stop routes.
  Manager routes unchanged.
- `foreman/cli.py` — `blocked_kind` in `foreman task show` and `foreman board`,
  `blocked_gate`/`blocked_engine` totals in `foreman status`, `foreman engine
  status` and `foreman task unblock` moved onto the shared derivations, and the
  CLI-local copies of `default_command_requester` and `_engine_is_paused`
  removed.
- `frontend/src/api.js`, `App.jsx`, `components.jsx`, `format.js`,
  `styles.css` — the engine header ("Engine: resident / paused / not running"
  with the heartbeat age), Stop renamed to Pause, dead-letter badges on blocked
  cards and in the project header.
- `foreman/dashboard_frontend_dist/` — rebuilt.
- Tests: `tests/test_dashboard.py`, `tests/test_cli.py`,
  `frontend/src/*.test.js(x)`.
- Docs: `docs/MANUAL.md` (§17 Run/Pause, dead-letter kinds, endpoint map,
  troubleshooting; `task unblock` semantics), `README.md`,
  `docs/ARCHITECTURE.md`, `CHANGELOG.md`,
  `docs/adr/ADR-0002-dashboard-data-access-boundary.md`,
  `docs/sprints/current.md`, `docs/STATUS.md`.

## Migrations

- none. `blocked_kind` is derived from the task's persisted step and the
  project's workflow definition; the engine state comes from the existing
  `leases` and `engine_commands` rows.

## Risks

- **An action returns when the command is queued, not when it lands.** Pause no
  longer produces an immediate visible change in task state. Mitigated by
  showing engine state and the command log, so a pending order is visible.
- **`paused` is derived from the command log**, because the flag itself lives
  in the serve process's memory. It is correct for every state reached through
  a command and wrong only for an engine paused by something that left no
  command row — which nothing currently does.
- **The spawn fallback is single-machine.** It starts an engine on the host
  running the dashboard. A multi-host deployment must replace the injected
  spawner rather than rely on it.
- **`foreman task unblock` behaviour changed**: it now refuses only the `gate`
  kind. A task the engine blocked at a persisted resume step used to be
  un-unblockable; that was a bug, and the existing gate-refusal test still
  passes.

## Tests

- `./venv/bin/python -m unittest discover -s tests` — 754 tests, OK (1 skipped).
- `npm --prefix frontend test` — 29 tests, 3 files, passing.
- `npm --prefix frontend run build` — clean; `foreman/dashboard_frontend_dist/`
  rebuilt.
- `./venv/bin/python scripts/validate_repo_memory.py` — passing.

New coverage: the status shape (resident, not resident, paused from the command
log), start when resident vs not resident through a fake spawner injected into
the service, start with a task id queueing `run_task`, pause queueing `pause`
and changing no task status, task stop queueing `stop_task`, the command
listing and its status filter, blocked kinds across the board/detail/summary
payloads, and CLI coverage for `task show`, `board`, `status`, and the
engine-dead-letter unblock. No test invokes a real `claude` or `codex` binary.

## Screenshots or output examples

```console
$ foreman board foreman
Progress: done=1/5 | in_progress=1 | blocked=2 (gate=1 engine=1) | todo=1 | cancelled=0
...
Blocked (2)
- task-gate | feature | Paused review | step=human_approval | blocked_kind=gate | reason=Awaiting human approval
- task-engine | feature | Loop limit | step=develop | blocked_kind=engine | reason=Step 'develop' exceeded its visit limit

$ foreman task show task-engine
Status: blocked | type=feature | created_by=human
Current step: develop
Blocked kind: engine (blocked by the engine; clear with `foreman task unblock`)
Blocked reason: Step 'develop' exceeded its visit limit

$ foreman status
Tasks: todo=1 in_progress=1 blocked=2 done=1 cancelled=0
Blocked: gate=1 engine=1

$ curl -s localhost:8080/api/projects/foreman/agent/status
{"resident": true, "paused": false, "state": "resident", "holder_id": "serve-9f2c1d",
 "heartbeat_age_seconds": 4.2, "heartbeat_at": "2026-09-04T21:34:43.366128Z",
 "lease_expires_at": "2026-09-04T21:36:43.366149Z", "lease_expired": false,
 "current_task": null, "project_id": "foreman",
 "commands": [{"id": "cmd-dd6953c316b1", "command": "resume", "status": "completed",
               "task_id": null, "requested_by": "dashboard", ...}]}
```

Dashboard header: `Engine: resident · heartbeat 4s ago` next to a **Pause**
button; with nothing resident, `Engine: not running` next to **▶ Run**.

## Acceptance criteria satisfied

- `GET /api/projects/{id}/agent/status` reports residency, holder, heartbeat
  age, pause state, current task, and recent commands — from the engine lock
  view and the command table.
- Start enqueues `resume` when resident and otherwise spawns a detached
  `foreman serve` through an injectable spawner; stop enqueues `pause` and
  changes no task status; task stop enqueues `stop_task`.
- `_RUNNING_PROCS` and the process-handle helpers are gone from
  `foreman/dashboard_service.py`.
- Blocked tasks carry `blocked_kind` in the API, `foreman task show`, and
  `foreman board`; project summaries and `foreman status` report
  `blocked_gate`/`blocked_engine`.
- The header shows engine state with the heartbeat age, its stop control
  pauses, blocked tasks show their kind, and the dist bundle is rebuilt.
- Backend suite, frontend tests, frontend build, and the repo-memory validator
  all pass.
- `docs/MANUAL.md`, `README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`, the
  ADR-0002 amendment, and this note are updated.

## Follow-ups

- The dashboard has no view of the command log yet beyond the status payload's
  last ten; `GET /api/projects/{id}/engine/commands` is wired but unused by the
  UI. A command history panel is the natural next surface.
- The engine header polls with the project scope refresh. Once the intake slice
  lands, folding engine state into the SSE stream would remove the poll.
- `requested_by` defaults to the literal `"dashboard"` because a shared token
  is not identity. It becomes a real actor when API tokens land in slice 3.
