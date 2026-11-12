# fix/review-sees-the-whole-change

## Summary

Found by running sprint 58 through Foreman. A 1,310-line change was approved
by the reviewer in 7 seconds.

## What happened

The review prompt carries the branch diff capped at `review_diff_max_chars`
(16,000 by default), head and tail kept, the middle replaced by
`[...truncated N chars...]`. The prompt did not say what that line means, so
the reviewer decided on what it was shown. The merge gate (a person) read the
whole diff; the reviewer did not.

## Scope

- Reviewer role prompts: a truncated diff means the change has not been seen;
  read the changed files in full before deciding.
- `.gitattributes`: `foreman/dashboard_frontend_dist/**` is `-diff`, so the
  committed bundle shows as changed without filling the capped diff.

## Files changed

Reviewer role files, `.gitattributes`, changelog.

## Migrations

None.

## Risks

Reviews of large changes take longer and cost more. That is the point.

## Tests

Whole suite. The effect on reviews is observed on the next sprint 58 tasks
and recorded in `docs/sprints/current.md`.

## Follow-ups

- The engine could refuse to accept an approval from a run that used no
  tools when the diff was truncated. Not built.
- This project's cap is raised to 120,000 characters in its settings.
