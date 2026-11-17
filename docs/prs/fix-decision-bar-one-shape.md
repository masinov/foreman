# PR Summary: fix/decision-bar-one-shape

## Summary

- A task's decision bar always puts the question on its own line and its
  facts on the line below (owner, 2026-11-17: the two bars looked different
  for no reason a person could see).

## Scope

- One rule in `frontend/src/styles/task.css`, and a test of it.

## Files changed

- `frontend/src/styles/task.css`, `frontend/src/pages/task/TaskPage.test.jsx`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- A decision with few facts is one line taller than before.

## Tests

- Frontend lint, tests and build. In a browser on a copy of the live
  database: a merge approval, a blocked task and a backlog task measured
  with the facts under the question in each.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The same shape for every decision, at every width.

## Follow-ups

- none
