# PR Summary: fix/engine-records-on-their-task

## Summary

- The end of sprint 62, slice 3, after the owner's go on the two questions
  ADR-0037 left open.
- **A task's Activity lists every record the engine kept on it.** It used to
  leave out the ones whose text did not quote the task's id. That rule was
  there to hide records pinned to the task from elsewhere, which ADR-0037
  ended. It also hid blocks that the sprint's Activity listed. In the live
  database these are FOR-3 (a failed `git checkout`) and FOR-14 and FOR-15
  ("Default branch 'main' HEAD changed …"). A task's Activity now lists at
  least what its sprint's lists about it.
- **The sprint's Activity no longer leaves out runs at the `orchestrator`
  step.** The ones left are about a task: a run recovered, a block before
  any step.
- **The worktree clean-ups are the project's records.** These are
  `engine.worktrees_reclaimed`, `engine.worktree_limit_exceeded` and
  `engine.worktree_reclaim_failed`. They are about other tasks' worktrees,
  removed to stay under `max_live_worktrees`, and the payload names the
  task that needed the room (`for_task_id`).
- **Decided:** a sprint's Activity does not list the sprint's own records,
  as each level's Activity lists what it holds.

## Scope

- `foreman/store/runs.py`:
  - `list_task_runs_page` no longer filters the engine's records by
    detail;
  - `list_sprint_activity_page` loses `skip_steps`.
- `foreman/domain/activity.py`: `RECORD_STEPS` is removed, and the comments
  say the rule.
- `foreman/services/task_reads.py`.
- `foreman/engine/task_worktrees.py`: the clean-ups go through
  `emit_project_event`, and the task's `emit_event` is removed.
- `frontend/src/pages/shared/activityWords.js`: a comment only.
- `frontend/src/styles/ui.css`: a long unbroken value in a Details list
  (the full commit ids in FOR-14's block reason) breaks inside its column
  instead of running past the page's edge. Seen at desktop and phone width
  on a copy of the live database.

## Files changed

- Code as above.
- Tests: `tests/test_dashboard_task_reads.py` (one new test, two updated)
  and `tests/test_worktrees.py`.
- Docs:
  - ADR-0037 (amended, with the decision);
  - `docs/MANUAL.md`, `CHANGELOG.md`;
  - `docs/sprints/current.md`, `docs/sprints/backlog.md`.

## Migrations

None. The live database holds no worktree clean-up records to move.

## Risks

- A task's Activity shows more rows for tasks the engine blocked or
  stopped. These are the same rows its sprint's Activity already showed.

## Tests

- Both suites, lint and build. Counts are in `docs/STATUS.md`.

## Acceptance criteria

- What a sprint's Activity lists about a task is in the task's Activity.
- No record about the project's worktrees is written on a task.

## Follow-ups

None.
