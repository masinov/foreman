# PR Summary: feat/reopen-sprint-and-decline-only

## Summary

- Sprint 60, decision 8 (owner): a finished sprint can be reopened, and in
  the backlog Decline is the one way to say "we won't do this".

## Scope

- `SPRINT_TRANSITIONS`: `completed` may go back to `active`, refused while
  another sprint is active, as activating one is. A cancelled sprint
  stays closed. The sprint page shows "Reopen sprint" on a finished
  sprint; `foreman sprint activate` does the same.
- Task page: an accepted backlog task's More menu has Decline (with an
  optional reason) where it had Cancel. A filed one already had Decline in
  its decision. The API still cancels a backlog task, because a confirmed
  split proposal cancels the task it replaces, wherever that is.
- Docs: ADR-0025 amendment, MANUAL (sprint commands).

## Tests

- `test_a_finished_sprint_can_be_reopened_and_a_cancelled_one_cannot`;
  the sprint page test (a finished sprint offers Reopen sprint); the task
  page action tests (Decline in More, confirmed and refused). The full
  suites.
