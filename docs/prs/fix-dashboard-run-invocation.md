# PR: fix/dashboard-run-invocation

## Summary

- Confirmed the dashboard `Run` control was spawning the Foreman CLI with an
  invalid `--project` flag.
- Fixed the subprocess argv to match the shipped CLI contract:
  `foreman run <project_id> --db <path>`.
- Added dashboard regression coverage that asserts the exact argv passed to
  `subprocess.Popen` for both project-scope and task-scope starts.

## Scope

- `foreman/dashboard_service.py`
- `tests/test_dashboard.py`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`

## Files changed

- `foreman/dashboard_service.py`
- `tests/test_dashboard.py`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/prs/fix-dashboard-run-invocation.md` (new)

## Migrations

None.

## Risks

- The regression tests verify spawned argv via mocking; they do not execute a
  full background dashboard-triggered run.
- This slice does not change broader dashboard subprocess lifecycle handling.

## Tests

- `./venv/bin/foreman run --help`
- `./venv/bin/foreman run --project demo --db /tmp/demo.db`
- `./venv/bin/python -m pytest tests/test_dashboard.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Acceptance criteria satisfied

- Dashboard `Run` now matches the actual CLI parser contract
- Regression coverage asserts the exact argv used for subprocess launch
- Repo-memory docs updated to record the slice and remove the closed follow-up

## Follow-ups

- Add browser-driven validation for the dashboard Run/Stop controls
- Persist meta-agent session history to SQLite
