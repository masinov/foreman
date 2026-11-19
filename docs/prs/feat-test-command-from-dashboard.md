# PR Summary: feat/test-command-from-dashboard

## Summary

- Sprint 60, decision 4 (owner, 2026-11-19): the test command is edited in
  the dashboard.

## Scope

- `test_command` leaves `HOST_LEVEL_SETTINGS`. The API accepts it and the
  settings page shows it as a field under Tests.
- The form refuses an edit that empties it, since `_builtin:run_tests`
  fails without a command.
- ADR-0017 amendment: why the test command differs from the settings that
  stay terminal-only. `docs/MANUAL.md`'s list of host-level settings
  updated.

## Migrations

- none

## Risks

- A dashboard token holder can set the command the engine runs. They could
  already start agents that run commands on the host.

## Tests

- `tests/test_dashboard_safety.py` (host-level settings now shown with
  `worktree_setup_command`; a new test that the test command is set over the
  API), frontend (451), lint, build; a screenshot of the Tests section on a
  copy of the database.
