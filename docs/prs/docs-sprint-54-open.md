# PR Summary: docs/sprint-54-open

## Summary

Opens sprint 54 (Phase 1 of the production readiness review: resident
engine and intake) and records the live-run protocol: slices are planned by
hand as dogfood tasks and executed through `foreman run foreman`, with the
engine's behavior recorded in `docs/reviews/sprint-54-live-run-notes.md`.

## Scope

- `docs/sprints/current.md`: sprint 54 goal, six slices, decisions taken at
  open (GitHub for pull-request integration; identity provider and
  notification channel undecided), live-run protocol.
- `docs/STATUS.md`: current sprint and focus.
- `docs/sprints/backlog.md`: Phase 1 entries annotated with the sprint that
  takes them.
- `docs/reviews/sprint-54-live-run-notes.md`: the live evaluation log,
  started with the setup and the first observations.

## Files changed

- `docs/sprints/current.md`, `docs/STATUS.md`, `docs/sprints/backlog.md`,
  `docs/reviews/sprint-54-live-run-notes.md`, `docs/prs/docs-sprint-54-open.md`

## Migrations

- none

## Risks

- none (documentation only)

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- sprint 54 is the active sprint in repo memory with concrete slices,
- the live-run protocol is written down before the first engine run.

## Follow-ups

- slice 1 (`foreman serve`) as a dogfood task run by the engine.
