# ADR-0018: Completion Evidence Is Facts, Not A Score

- Status: accepted
- Date: 2026-11-11
- Deciders: engine team

## Context

Before a merge the engine builds `CompletionEvidence` and a guard decides
whether the task may land. Until now the evidence carried a 0 to 100 score
(40 for criteria, 20 for the number of changed files, 10 for diff size, 30
for tests) and a verdict ladder derived from it (strong, adequate, weak,
insufficient). The 2026-11-10 review found three problems:

- The default criteria check was keyword overlap between each acceptance
  criterion and the developer's own summary. A summary that repeated the
  criteria scored as full coverage. Nothing had been checked.
- The test result was not tied to a commit. Tests that passed, followed by
  more commits, still counted as passed for the new head. The same held for
  a review approval.
- A number invites trust it has not earned. Points for touching more files
  measure nothing about correctness, and the dashboard showed "72/100".

## Decision

1. Evidence records facts and nothing weighted from them. The score, its
   breakdown, the verdict and its reasons are removed from the model, the
   events, the API payload, the digest, the reviewer prompt and the UI.
2. Each check is tied to the commit it was about. `engine.test_run` carries
   `head_sha`; a new `engine.review_recorded` event carries the branch head
   at the moment a decision role answered. Evidence has `tests_status`
   (`passed`, `failed`, `not_run`, `stale`), `tested_sha`, `reviewed_sha`
   and `security_reviewed_sha`. `stale` means the tests ran on a commit that
   is no longer the branch head.
3. Acceptance criteria are machine-checked only by a configured judge model.
   Without one, or when its call fails, every criterion has status
   `unverified` and `judged_by` is `none`. The keyword heuristic is deleted.
4. `proof_status` is:
   - `failed` when the tests failed or are stale, when an approving code
     review is of an older commit, when a judge did not pass a criterion and
     no code review has approved, or when an implementation task has no
     acceptance criteria;
   - `pending` when nothing failed but something has not happened yet (tests
     not run; criteria neither judged nor covered by an approving review).
     What is missing is listed in `outstanding`;
   - `passed` otherwise: tests passed on the head commit, and the criteria
     were all passed by a judge or are covered by an approving code review of
     the head commit.
5. The merge guard is unchanged in shape: it needs `proof_status == passed`,
   an approving code review, a non-empty delta that is not docs or tests
   only, and a security approval on the secure workflow. Waivers still cover
   missing or unmet criteria and never tests or review.
6. Evidence is rebuilt after each decision step, so a task waiting at the
   merge gate shows the review that happened rather than the state from
   before it.
7. Evidence stored before this ADR still loads: unknown keys are ignored. A
   test or review recorded without a commit is taken at face value.

## Consequences

- With no judge configured, the engine no longer claims any criterion is met.
  Code review carries that responsibility, and the reviewer prompt says so.
- A reviewer that commits to the branch invalidates its own approval and the
  test result; the merge is blocked with the two commits named. The fix is
  to run the test and review steps again, not to trust the older result.
- A task with thin evidence but passing tests is no longer blocked for a low
  score. The delta checks (no changes; docs or tests only) remain.
- Consumers of `engine.completion_guard` and of the task payload lose
  `verdict` and `score` and gain `proof_status`, `tests_status`, the SHAs
  and `outstanding`.
- Still open in the backlog: a judge on by default, and acceptance tests in
  a path the developer role cannot edit.
