# PR Summary: feat/task-api-a-task-s-changed-files-and-diff-and-its-checks-as-facts-and-claims

## Summary

- Five reads under `/api/v1` for the task page: changed files, one file's
  diff, checks as facts and claims, paged runs, and a run's prompt and
  transcript. Python only.

## Scope

- `GET /tasks/{id}/changes`, `GET /tasks/{id}/changes/diff?path=`,
  `GET /tasks/{id}/checks`, `GET /tasks/{id}/runs`, `GET /runs/{id}/output`,
  each with a pydantic response model.
- The task detail still carries its full `runs` list as before; the new paged
  route is the one the task page should use.
- Out of scope: frontend, evidence file capture (`evidence_files` is always
  empty; its item shape is in the response model).

## Files changed

- `foreman/git.py`: `FileChange`, `branch_changes`, `file_diff`, `merge_base`,
  `commits_ahead`. Fixed argument lists, no shell, `--literal-pathspecs`.
- `foreman/dashboard_task_reads.py`: the reads.
- `foreman/dashboard/task_models.py`: response models and the caps.
- `foreman/dashboard/routers/tasks.py`, `foreman/dashboard/context.py`
  (`with_store`), `foreman/store/runs.py` (`list_task_runs_page`).
- `tests/test_dashboard_task_reads.py`, `docs/ARCHITECTURE.md`.

## Migrations

- none

## Risks

- Diffs and changes are computed on request against the repository's branch
  refs, so a merged and deleted branch shows no changes (with the reason).
- A path that is not valid UTF-8 is decoded with replacement and will not
  match; such a file lists but its diff request is a 400.
- The test result line is the last non-empty line of the recorded output tail.
- Caps are in characters: diff 200,000; prompt and transcript 200,000 each.
  A transcript over the cap keeps its earliest entries.
- Tests facts are read from the latest `engine.test_run` event, with `stale`
  judged against the live branch head, so they are right before evidence has
  been built.

## Tests

- `tests/test_dashboard_task_reads.py` (15 tests, real temporary git
  repository): changes with every status, no branch, missing branch, 404,
  diff, rename diff, unchanged path, traversal/glob/option/pathspec-magic
  paths, missing path, diff cap, checks with full evidence and with none,
  stale tests, runs paging, run output, output cap.
- Full suite: 1221 tests OK (1 skipped); `ruff check` passes (removed a duplicate `"sprint_id"` key in `get_task` that it flagged).

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Endpoints exist under `/api/v1` with response models and are described in
  `docs/ARCHITECTURE.md`.
- Tests cover every listed case.
- No git command is built by interpolating request input.

## Follow-ups

- Evidence files (Phase 5) fill `evidence_files`.
- The Task page slice consumes these routes.
