# fix/worktree-self-heal

## Summary

Sprint 56 slice 3b. Two worktree behaviours that could lose work or stall
every merge.

## Scope

- `WorktreeManager.ensure_integration` aborts an unconcluded merge in the
  integration tree before using it. Only the engine merges there and it
  concludes or aborts each merge, so an unconcluded one is a killed engine's
  leftover. If the abort fails, a `WorktreeError` says so.
- `WorktreeManager._checkout` no longer passes `--force`. A tree on the wrong
  branch with changes to tracked files raises a `WorktreeError` naming the
  tree and both branches; the orchestrator already turns that into a blocked
  task with the message. A clean tree is moved back as before.

Other uncommitted changes in the integration tree are not discarded; the merge
preflight still reports them (`dirty_worktree`).

## Files changed

- `foreman/worktrees.py`
- `tests/test_worktrees.py`
- `CHANGELOG.md`, `docs/sprints/current.md`

## Migrations

None.

## Risks

A task whose tree strayed to another branch with uncommitted changes now
blocks with a message where it previously continued after silently discarding
them. That is the intended trade.

## Tests

Three new tests in `tests/test_worktrees.py`; full suite and `ruff check`.

## Acceptance criteria satisfied

Slice 3b as written in `docs/sprints/current.md`.

## Follow-ups

None.
