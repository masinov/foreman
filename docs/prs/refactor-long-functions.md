# PR Summary: refactor/long-functions

## Summary

- The seven functions ADR-0032 listed as over 200 lines are split into
  named parts. No behaviour change.

## Scope

- `foreman/engine/agent_step.py` (`execute_native`, `_native_config`,
  `_NativeRunTally`), `foreman/engine/workflow_runner/agent_steps.py`
  (`_run_agent_step` and its parts, `_Attempt`),
  `foreman/engine/resident/base.py` (`run`, `_iterate`, `_run_pass`,
  `_after_pass`, `_after_failed_pass`, `_ServeLoop`), `foreman/api/app.py`
  (`create_dashboard_app` and five `_add_*`/`_prepare_*` parts),
  `foreman/engine/evidence.py` (fact readers),
  `foreman/engine/builtins/merge.py` (`_guard_completion`, `_landed`,
  `_not_landed`, `_merge_failed`), `foreman/cli/tasks/register.py` (one
  function per subcommand).

## Files changed

- The seven above, ADR-0032, CHANGELOG, backlog, sprint file.

## Migrations

- none

## Risks

- A control-flow refactor of the engine's loop and agent step. The
  existing tests cover each branch (shutdown, lock lost, quota, lease lost,
  a failed task, a targeted run that cannot start, a corrective retry, an
  unread approval); the full suite passes unchanged.

## Tests

- Full suite unchanged and passing; ruff, `lint-imports`.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- No function in `foreman/` is over 200 lines.

## Follow-ups

- none
