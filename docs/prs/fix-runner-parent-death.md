# PR Summary: fix/runner-parent-death

## Summary

- Sprint 55 slice 4. An engine that dies no longer leaves its agent running.

## Scope

- `foreman/runner/process.py`: SIGHUP joins the shutdown signals;
  `popen_kwargs` adds a pre-exec hook that sets the Linux parent-death
  signal (SIGTERM) when the child is started from the main thread.

## Files changed

- `foreman/runner/process.py`, `tests/test_runner_lifecycle.py`
- `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- Linux only; other platforms keep the previous behaviour.
- The signal reaches the agent process, not processes it started. Claude
  Code stops its own tools on SIGTERM; a tool that ignores that survives.
- `preexec_fn` runs between fork and exec; the hook does one `prctl` call
  and swallows every error.

## Tests

- `python -m unittest discover -s tests`: 1022 pass, 1 skipped (3 new,
  including a real engine process killed with SIGKILL)

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Killing the engine with SIGKILL stops the child it started.
- Closing the engine's terminal stops its agents and settles the run.

## Follow-ups

- Manager chat subprocess onto the runner (Phase 5).
