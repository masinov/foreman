# PR Summary: fix/lease-fencing-on-writes

## Summary

- The engine's task writes carry the fencing number of the task lease they
  are made under; the store refuses a write when a newer lease exists, and
  the engine stops without touching the task (ADR-0011 amendment).

## Scope

- `foreman/domain/errors.py` (`FencedWriteError`), `foreman/store/tasks.py`
  (`update_task_engine_state(fencing_token=)`), `foreman/engine/leasing.py`
  (fencing numbers kept per held lease), `foreman/engine/task_writes.py`,
  `foreman/engine/orchestrator/base.py`.

## Files changed

- The five above, `tests/test_leases.py`, `tests/test_runner_lifecycle.py`,
  ADR-0011, ARCHITECTURE, CHANGELOG, backlog, sprint file.

## Migrations

- none (the column existed since the lease table was added).

## Risks

- A write is refused only when a newer lease exists, never for a lease that
  merely lapsed, so a busy database cannot cost a finished step.

## Tests

- `FencedTaskWriteTests` (store): the holder writes; a replaced holder is
  refused and nothing is written; a lapsed lease nobody took still writes;
  a write without a lease is not fenced.
- `test_a_write_under_a_replaced_lease_is_refused_even_with_no_renewal_between`
  (engine): fails without the fence (the task moved to `test` under the new
  holder), passes with it.
- Full suite, ruff, `lint-imports`.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A holder whose lease was taken over cannot write the task.

## Follow-ups

- none
