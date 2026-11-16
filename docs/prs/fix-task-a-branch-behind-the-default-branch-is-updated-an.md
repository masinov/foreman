# fix/task-a-branch-behind-the-default-branch-is-updated-an

## Summary

The merge step no longer merges a branch that lacks the default branch's head. It merges the default branch into the task branch in the task's own worktree, returns the new outcome `updated`, and the shipped workflows send the task back to `test` (ADR-0026).

## Scope

`_builtin:merge`, the outcome constant and normalisation, `_BUILTIN_OUTCOMES`, `_OUTCOME_ORDER`, the three shipped workflows, docs.

## Files changed

`foreman/builtins.py`, `foreman/outcomes.py`, `foreman/workflows.py`, `foreman/dashboard_definitions.py`, `foreman/data/workflows/development*.toml`, `tests/test_builtins.py`, `tests/test_engine_branches.py`, `docs/adr/ADR-0026-*.md`, `docs/adr/README.md`, `docs/ARCHITECTURE.md`, `docs/MANUAL.md`, `CHANGELOG.md`.

## Migrations

None.

## Risks

A project's own workflow without a `merge` + `completion:updated` transition blocks at the fallback. A branch that keeps falling behind costs another test, review and approval per round.

## Tests

Real-git tests for behind, conflicting and not-behind branches, the operator's checkout untouched, a full development-workflow run through update, test, review, approval and merge, and the wiring of the outcome.

## Acceptance criteria satisfied

All listed in the task.

## Follow-ups

None.
