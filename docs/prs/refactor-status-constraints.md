# refactor/status-constraints

## Summary

Sprint 56 slice 11: database guards for the status vocabularies, one settings
accessor, dead code removed.

## Scope

- Migration 20 adds BEFORE INSERT and BEFORE UPDATE OF triggers on
  `tasks.status`, `tasks.task_type`, `tasks.complexity` (NULL allowed),
  `sprints.status`, `runs.status` and `projects.autonomy_level`. A write
  outside the vocabulary aborts with `invalid <table>.<column>`.
- `settings.settings_of(project)` returns the validated `ProjectSettings`.
  The orchestrator, builtins, worktrees, context projection and `init` read
  through it. Removed: `_int_setting`, `_bool_setting`, `_float_setting`,
  `_string_setting` (two copies), and the hand-rolled parsing in
  `worktrees.py`. In `worktrees.py` an invalid setting surfaces as
  `WorktreeError`, which its callers already handle.
- `runner_max_cost_usd` default 1000.0 -> 0.0 in the model.
- Removed `foreman/events.py` and its tests, `api_tokens.secrets_match`,
  `builtins._task_branch_has_committed_delta`,
  `git.assert_not_on_default_branch`, `notifications.describe_policies`,
  `signals._parse_signal_line`, `WorkflowGateSteps.loaded`.

## Files changed

`foreman/migrations.py`, `settings.py`, `orchestrator.py`, `builtins.py`,
`worktrees.py`, `context.py`, `cli.py`, `api_tokens.py`, `git.py`,
`notifications.py`, `engine_control.py`, `runner/signals.py`;
`foreman/events.py` and `tests/test_events.py` deleted; tests; docs.

## Migrations

Migration 20 (triggers only; no rows are rewritten). The live database was
checked first: every stored value is inside the vocabulary.

## Risks

- A project whose stored settings are invalid now fails where a setting is
  read (worktree listing, context projection), not only at run start.
  Settings are validated on every write path, so this needs a hand-edited
  database.
- Any external writer that stored an out-of-vocabulary status will be
  refused.

## Tests

Full Python suite and `ruff check`.

## Acceptance criteria satisfied

Slice 11 as written in `docs/sprints/current.md`, except Python `Enum`
classes, which are left to the Phase 3 restructuring.

## Follow-ups

Sprint 56 close-out; Phase 3.
