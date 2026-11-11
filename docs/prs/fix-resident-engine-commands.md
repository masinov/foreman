# fix/resident-engine-commands

## Summary

Sprint 56 slice 10b (review finding E10).

## Scope

- `ResidentEngine.attach()` and `settle_interrupt()` are public; `foreman
  run` builds an engine with `accepts_run_requests=False` and
  `honour_standing_pause=False`, attaches it, and settles a command that
  interrupts its step (exit 130, with who sent it).
- A starting resident engine adopts a standing pause (the last applied
  pause/resume in the command log).
- `run_task`: queued requests keep their command, which is finished after
  the pass (`completed` with what happened, or `rejected` when the task could
  not start). Commands left `acknowledged` by an engine that stopped are
  settled at startup: `run_task` and `resume` are applied, the rest rejected.
- Any exception other than the handled ones ends the loop as `crashed`, exit
  code 1, with the traceback in the `serve.crashed` log line; agent processes
  are terminated and the lock is released as before.
- `ForemanStore.project_activity_token`; the idle wait compares it after a
  `data_version` change and keeps waiting when it is unchanged.

## Files changed

`foreman/serve.py`, `foreman/cli.py`, `foreman/store.py`,
`tests/test_serve.py`, changelog, sprint.

## Migrations

None.

## Risks

- An operator who paused a project and later starts `foreman serve` by hand
  gets a paused engine; `foreman engine resume` (or the dashboard) starts it.
  The `serve.started` log line carries `paused`.
- The activity token reads the project's tasks on each foreign commit while
  idle; cheap for the sizes Foreman handles, and it replaces a full pass.

## Tests

Full Python suite and `ruff check`. The one-shot path is covered at the
engine level (attach, refusal of run requests); there is no end-to-end CLI
test of interrupting `foreman run`.

## Acceptance criteria satisfied

Slice 10b as written in `docs/sprints/current.md`.

## Follow-ups

Slice 10c.
