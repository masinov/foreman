# PR Summary: docs/backlog-tests-direction

## Summary

- Records the owner's direction of 2026-11-22 in the backlog: tests that
  Foreman can see one by one and control. It covers which tests ran, what
  each checks, where a task shows them, and which suites apply to which
  work.
- Recorded, not scheduled. A survey, an ADR and a mockup come before code.

## Scope

- Docs only.

## Files changed

- `docs/sprints/backlog.md`
- `docs/prs/docs-backlog-tests-direction.md`

## Migrations

- None.

## Risks

- None. No behavior changes.

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`

## Acceptance criteria satisfied

- The direction is in the backlog with what Foreman knows today, what is
  wanted, and what to survey first.

## Follow-ups

- The test count in "A task's Activity, step by step" should be read from
  the same report, so that work carries over.
