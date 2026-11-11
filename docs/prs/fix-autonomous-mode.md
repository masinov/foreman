# fix/autonomous-mode

## Summary

Sprint 56 slice 10c (review finding E14), plus a defect the new tests
exposed: autonomous tasks had no branch or worktree.

## Scope

- Branch and worktree are assigned for every task, not only in directed mode
  (ADR-0012 amendment; spec §6.2 deviation recorded in `docs/STATUS.md`).
- The two blocking "autonomous contract" checks are replaced by one event,
  `workflow.autonomous_contract_missing`, emitted once per task after a step
  whose role may send `task_started` while the task still has the
  placeholder title. Whether it was already emitted is read from the store.
- `_task_started_received` and `_developer_step_executed` are gone.
- `signal.task_started`: `task_type` must be a known type; `branch` must be a
  valid ref name, exist, and not be the default branch. A refused field
  emits `signal.rejected` with `field` and `reason`; other fields apply.
- The agent-facing contract text in the context projection matches.

## Files changed

`foreman/orchestrator.py`, `foreman/context.py`,
`tests/test_autonomous_mode.py` (new), ADR-0012, `docs/ARCHITECTURE.md`,
`docs/STATUS.md`, changelog, sprint.

## Migrations

None.

## Risks

- An autonomous project that relied on the agent working in the operator's
  checkout now gets a worktree per task. That is the behaviour ADR-0012
  already promised.
- With the completion guard on, an unnamed task reaches the merge step and
  is blocked there for missing acceptance criteria, after a review has been
  paid for. The alternative (blocking earlier) is what the spec rules out.

## Tests

Full Python suite and `ruff check`.

## Acceptance criteria satisfied

Slice 10c as written in `docs/sprints/current.md`.

## Follow-ups

Slice 11.
