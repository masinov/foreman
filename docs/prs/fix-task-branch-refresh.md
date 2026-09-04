# PR Summary: fix/task-branch-refresh

## Summary

Sprint 54 live-run fix F3. Task 2's branch was created at 12:32 and reached
the merge gate at 18:07; in between, `main` had taken the quota fix, which
touches the same files, so the engine's merge conflicted and cost a full
develop, test, and review cycle. That resolution pass was then cut off by a
quota reset with the merge half concluded, and the existing conflict-recovery
path would have aborted it on the next visit. Three changes:

1. every develop visit first merges the default branch into the task branch
   when the branch is behind and the merge is clean, so a task that waited
   (gate, quota, review round) works on current code and the final merge
   cannot conflict on changes the developer never saw;
2. an unconcluded merge left in the working tree is never aborted; the
   developer is told to finish it;
3. `foreman approve` and `foreman deny` report a quota pause in the resumed
   workflow honestly and exit 75, instead of "Failed to approve".

## Scope

- `foreman/git.py`: `commits_behind(repo, branch, base)` and
  `merge_in_progress(repo)`.
- `foreman/orchestrator.py`: `_prepare_task_branch_for_step` gains the
  merge-in-progress guard (mode `merge_in_progress`) and, when the carried
  output is not merge-conflict feedback, calls the new `_refresh_task_branch`
  (mode `refresh` on success with `commits_behind`, `refresh_conflict` with
  guidance on a conflict; the merge is aborted in that case so the tree stays
  clean). The conflict-recovery path is unchanged.
- `foreman/cli.py`: `QuotaPauseError` handling in the gate-decision handler.
- Tests: two new refresh tests; the two merge-conflict tests rewritten so
  `main` moves while the task waits at a human gate (the orchestrator forbids
  the default branch moving during a step, and a branch created before the
  first develop visit is now refreshed there by design).

## Files changed

- `foreman/git.py`, `foreman/orchestrator.py`, `foreman/cli.py`,
  `tests/test_orchestrator.py`
- `docs/MANUAL.md`, `CHANGELOG.md`, `docs/STATUS.md`,
  `docs/sprints/current.md`, `docs/reviews/sprint-54-live-run-notes.md`,
  `docs/prs/fix-task-branch-refresh.md`

## Migrations

- none

## Risks

- A refresh merge commit lands on the task branch before the developer's
  work; reviewers see it in the diff against `main` as an empty delta. The
  merge step already uses `--no-ff`, so history keeps both sides.
- A refresh is skipped when the working tree is dirty, so an interrupted
  pass that left uncommitted edits (no merge in progress) still gets the old
  behavior: the developer resumes on the stale branch and the merge step
  finds the conflict.

## Tests

- `tests.test_orchestrator`, `tests.test_quota_pause`,
  `tests.test_output_contract`, `tests.test_runner_lifecycle`,
  `tests.test_workflow_gates` in the clone (179 tests); the full suite and
  `scripts/validate_repo_memory.py` on `main` after the merge.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- a task that waited merges without a conflict cycle when the merge is clean,
- an interrupted merge survives the next visit,
- a quota pause after a gate decision is reported as a pause.

## Follow-ups

- Sprint 55: with pull requests and a remote default branch, the
  "default branch did not move during a step" invariant becomes a
  single-machine assumption to revisit.
