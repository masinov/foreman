# PR Summary: fix/old-evidence-reads-review-coverage

## Summary

- After the judge was removed, a task finished before 2026-11-19 showed its
  criteria as "Not reviewed yet", even when an approving review of its head
  had covered them. Its stored evidence said `unverified`, which then meant
  "no judge looked".

## Scope

- `CompletionEvidence.review_covers_criteria` and `criteria()`: a stored
  `unverified` criterion reads as `covered` when the evidence's code review
  approved the branch head. `criteria_line` says the same. The task's
  checks and the task payload read the checklist through `criteria()`.

## Tests

- `test_older_evidence_reads_its_approved_review_as_covering_the_criteria`
  (and a stale approval still reads as not covered); the evidence, task
  read, dashboard and prompt tests; the full suite.
