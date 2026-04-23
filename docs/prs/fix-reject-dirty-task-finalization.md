## Summary

Prevent Foreman from finalizing a task from dirty, uncommitted worktree state.

## Scope

- block `_builtin:merge` when the task branch has uncommitted changes
- block `_builtin:merge` when the task branch has no committed delta ahead of
  the default branch
- block `_builtin:mark_done` when the worktree is dirty
- require a recorded successful merge before `_builtin:mark_done` accepts an
  already-absorbed task branch
- add regression coverage for the false-finalization path exposed during the
  live sprint-46 rerun

## Files changed

- `foreman/builtins.py`
- `tests/test_orchestrator.py`
- `docs/STATUS.md`

## Migrations

- none

## Risks

- `_builtin:mark_done` now relies on a recorded successful merge run for
  already-absorbed branches; manual out-of-band merges without Foreman run
  history will be blocked until reconciled

## Tests

- `./venv/bin/python -m pytest tests/test_orchestrator.py -q -k 'CompletionGuardTests or MarkDoneCompletionGuardTests'`
- `./venv/bin/python -m pytest tests/test_orchestrator.py -q`
- `./venv/bin/python -m py_compile foreman/builtins.py`

## Acceptance criteria satisfied

- dirty task-branch state cannot be merged or marked done
- branches with no committed delta ahead of `main` cannot produce merge success
- already-absorbed branches require a recorded successful merge before
  finalization

## Follow-ups

- rerun the remaining sprint-46 tasks against this guard
- decide whether successful task completion should also require an explicit
  commit SHA recorded on the task or run
