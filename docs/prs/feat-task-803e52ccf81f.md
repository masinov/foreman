# feat/task-803e52ccf81f

## Summary

The project manager's context includes the backlog (ADR-0021), so it can
propose accepting, declining or planning filed and accepted work.

## Scope

- `foreman/meta_agent.py`: the state header gains a `### Backlog` block with
  filed, accepted and declined counts and the first 5 filed and first 5
  accepted tasks (id, type, truncated title). Declined work is counted, not
  listed.
- The operating contract gains a `Backlog:` block listing every
  `foreman backlog` subcommand (list, add, accept, decline, plan, unplan).
- Reads go through `store.page_backlog_tasks`; no new store code.

## Files changed

`foreman/meta_agent.py`, `tests/test_meta_agent.py`, this file.

## Migrations

None.

## Risks

The header grows by at most about 12 lines; it stays within its token bound.

## Tests

`tests/test_meta_agent.py`: backlog block names filed and accepted tasks and
respects the cap, omits declined and the backlog sprint row, handles an
absent backlog; the contract lists every backlog subcommand. The existing
drift test checks each contract line against the real parser.

## Acceptance criteria satisfied

Context names filed and accepted tasks (capped); the contract lists backlog
commands that exist; tests cover both.
