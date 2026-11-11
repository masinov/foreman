# PR Summary: fix/default-branch-check

## Summary

- Sprint 56 slice 3. The default branch may move while a task runs; only
  the task's own unreviewed commits reaching it is a violation.

## Scope

- `foreman/git.py`: `task_commits_on_default_branch` replaces
  `assert_default_branch_unchanged`.
- `foreman/orchestrator.py`: the post-step check uses it, with the default
  branch SHAs seen at step start and after the engine's branch refresh.

## Files changed

- `foreman/git.py`, `foreman/orchestrator.py`, `tests/test_orchestrator.py`
- `docs/adr/ADR-0012-worktree-per-task.md`, `docs/sprints/current.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- An agent that merges a newer default branch into its own branch by hand,
  after which the default branch receives that same merge, would be read as
  a leak. The engine does the refresh itself, so agents have no reason to.
- The old check also skipped dirty worktrees; the new one does not need to.

## Tests

- `python -m unittest discover -s tests`: 1041 pass, 1 skipped (3 new)
- `ruff check foreman tests scripts`: clean

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A commit on the default branch during a step does not block the task.
- A task whose commit is moved onto the default branch mid-step is blocked
  with `engine.branch_violation` and is not reviewed or merged.
- Commits a refresh brought in from the default branch are not counted.

## Follow-ups

- Slice 3b: integration worktree self-heal; no force checkout of a dirty
  task tree.
