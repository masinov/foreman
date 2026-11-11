# refactor/mutation-service

## Summary

Sprint 57 slice 4. One implementation of operator changes to tasks and
sprints, shared by the CLI and the dashboard.

## Scope

- `foreman/mutations.py`: `Mutations(store, via=, actor=)` with
  `accept_task`, `block_task`, `unblock_task`, `cancel_task`, `delete_task`,
  `transition_sprint`, `delete_sprint`; `MutationError`; `SPRINT_TRANSITIONS`.
- CLI: `task accept|block|unblock|cancel`, `sprint activate|complete` call
  it, stamped `via=cli` and the OS user. The CLI's own worktree-discard
  helper is removed.
- Dashboard service: `accept_task`, `cancel_task`, `delete_task`,
  `transition_sprint`, `delete_sprint` call it, stamped `via=dashboard`, and
  turn `MutationError` into a 400.
- Activity feed: summaries for the four new audit events.

## Behaviour changes

1. Audit events for accept, block, unblock and cancel from either surface,
   with `via`, `by`, `from_status` and the block reason.
2. Delete of a task with a running agent step under a resident engine is
   refused; so is delete of a sprint containing one.
3. The dashboard no longer completes a sprint with unresolved tasks.
4. `foreman sprint complete` on a planned sprint is refused.
5. `foreman task accept` on a non-triage task prints the same sentence as
   the dashboard.

## Files changed

`foreman/mutations.py` (new), `foreman/cli.py`,
`foreman/dashboard_service.py`, `frontend/src/format.js` and its test,
rebuilt bundle, `tests/test_mutations.py` (new), `tests/test_dashboard.py`,
`tests/test_intake.py`, changelog, sprint.

## Migrations

None.

## Risks

Item 3 changes what a button in the dashboard does: "Complete sprint" on a
sprint with open tasks now shows an error naming them. It is the rule the
engine and the CLI already used; reverting it is one condition in
`transition_sprint`.

## Tests

Full Python suite (1077 tests), `ruff check`, frontend `vitest` and build.

## Acceptance criteria satisfied

Slice 4 as written in `docs/sprints/current.md`, for status changes and
deletes.

## Follow-ups

Create and field-edit paths through the same service; an actor for
dashboard changes once login exists.
