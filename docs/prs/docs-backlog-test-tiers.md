# PR Summary: docs/backlog-test-tiers

## Summary

- At the owner's request (2026-11-24), two backlog entries from the
  question of when to run which tests:
  - **Owner direction 5:** tiers for Foreman's own test step. Each step
    runs the affected tests, picked by a tool and not by groups kept by
    hand. The merge runs the whole suite, and what is too slow for every
    merge runs before a release or on a schedule.
  - **Engineering:** run the Python suite in parallel, after checking that
    no tests share state.

## Scope

`docs/sprints/backlog.md` only.

## Files changed

- `docs/sprints/backlog.md`
- `docs/prs/docs-backlog-test-tiers.md`

## Migrations

None.

## Risks

None. Docs only.

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`

## Acceptance criteria

- Both entries are in the backlog, where the next planning reads them.

## Follow-ups

- The parallel suite, as a chore, when a sprint takes it.
