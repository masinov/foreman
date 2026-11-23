# PR Summary: docs/future-tests-and-views

## Summary

- Moves the owner's tests direction into the backlog's general future
  directions, as direction 5. It covers designing tests as well as watching
  them:
  - what must be tested (a component function, a full journey through the
    interface with a screenshot of the end screen);
  - suites, how tests run;
  - coverage, each requirement against reality;
  - a tester role.
- Adds direction 6: every view the owner has proposed is designed together,
  as one system, before any one is built.
- Roadmap stage 5 lists the statistics and tests views and says the views
  are designed together first.

## Scope

- Docs only. Replaces the standalone section added on
  `docs/backlog-tests-direction`.

## Files changed

- `docs/sprints/backlog.md`
- `docs/ROADMAP.md`
- `docs/prs/docs-future-tests-and-views.md`

## Migrations

- None.

## Risks

- None. No behavior changes.

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`

## Acceptance criteria satisfied

- Both directions are recorded where future design work starts. Each one
  says what exists today, what is wanted, and what is decided.

## Follow-ups

- A survey, then a design reference for the whole set of views (roadmap
  stage 5).
- The test count in "A task's Activity, step by step" should be read from
  a test report, so that work carries over to direction 5.
