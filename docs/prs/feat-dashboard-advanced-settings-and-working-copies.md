# feat/dashboard-advanced-settings-and-working-copies

## Summary

Items 8 and 9 of `docs/design/dashboard-v7/legacy-capabilities.md`: the last
things the old settings drawer could do that the rebuilt page could not.

## Scope

- General, "Advanced": merges land on (`default_branch`), specification
  (`spec_path`), reviewer reads at most (`review_diff_max_chars`), criteria
  judge (`judge_model`), judge reads at most (`judge_max_diff_chars`). The
  first two are kept on the project, so Save sends them beside `settings`.
- General, "Working copies": the tasks' copies counted against the limit, a
  row per copy saying what it is for and whether it is in use, and "Remove
  unused" (`POST /projects/{id}/worktrees/prune`), which never touches the
  copy merges land in or a live task's copy.
- Host-level values stay read-only under "This machine" (ADR-0017).

## Migrations

None. No API change.

## Risks

None known. "Remove unused" uses the same policy as `foreman worktree prune`.

## Tests

Frontend tests for both sections; the whole frontend suite and the Python
suite.

## Follow-ups

Live updates from the event streams; ESLint; docs.
