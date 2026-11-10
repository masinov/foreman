# PR Summary: fix/gate-decisions-through-engine

## Summary

- Sprint 55 slice 6. Approving or denying a task is now a recorded decision
  that the project's engine carries out, never an execution in the CLI or
  the web server.

## Scope

- `resume_human_gate(..., defer=True)`: one task write leaves the task
  `in_progress` at the next step.
- CLI `approve` / `deny` and the dashboard service use it and report
  whether an engine is resident.
- Dashboard: a neutral notice when a decision waits for an engine.
- A task paused at a human gate releases its lease.

## Files changed

- `foreman/orchestrator.py`, `foreman/cli.py`, `foreman/dashboard_service.py`
- `frontend/src/App.jsx`, `frontend/src/components.jsx`,
  `frontend/src/styles.css`, `foreman/dashboard_frontend_dist/*`
- `tests/test_orchestrator.py`, `tests/test_cli.py`, `tests/test_dashboard.py`
- `docs/adr/ADR-0011-resident-engine-and-project-lock.md`, `docs/MANUAL.md`,
  `docs/STATUS.md`, `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- Behaviour change for terminal users: `foreman approve` no longer merges
  by itself when no engine is running; it prints the command that does.
- The `Resume deferred:` line in the CLI output is replaced by an `Engine:`
  line; anything parsing the old line must change.

## Tests

- `python -m unittest discover -s tests`: 1032 pass, 1 skipped
- `npm --prefix frontend test`: 53 pass; build clean
- `ruff check foreman tests scripts`: clean

## Screenshots or output examples

- `Engine: none running; continue with `foreman run <project>` or
  `foreman serve <project>``

## Acceptance criteria satisfied

- No workflow step runs in a process that does not hold the engine lock.
- A deferred approval is continued by the engine's next pass.
- The web server returns from Approve without running an agent.

## Follow-ups

- Slice 7: first real engine run since these fixes, as the delegation trial.
- A named actor on decisions when identity exists (still `human`).
