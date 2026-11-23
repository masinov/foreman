# PR Summary: docs/backlog-tidy

## Summary

- The backlog's older lists were checked, item by item, against the code
  at `d8cebac` (owner, 2026-11-23: "what is left to finish the current
  product?"). Those lists covered:
  - the carried engineering items;
  - the defects found in sprints 58 and 60;
  - after ADR-0028;
  - the screen audit;
  - the dashboard follow-ups;
  - the finish plan;
  - the production readiness roadmap;
  - the review roadmap;
  - SSE;
  - the parking lot.
- What is still open is now one section, "Left to finish the current
  product". Its groups:
  - where the product does not hold together yet;
  - safety for work filed by other systems;
  - engineering;
  - items that belong to a later roadmap stage;
  - what was found already done.
- The old lists are kept as history in
  `docs/sprints/archive/backlog-lists-through-2026-11-23.md`.
- Found on the way: spec §6.4 is half built. A completed sprint is not
  tagged, no checkpoint note is written, and `write_checkpoint_notes` does
  nothing. This is recorded in `docs/STATUS.md` under the documented
  conflicts.
- `docs/sprints/current.md` no longer says the outcome numbers are on the
  pages. `docs/STATUS.md` has today's test counts.

## Scope

- Docs only.

## Files changed

- `docs/sprints/backlog.md`
- `docs/sprints/archive/backlog-lists-through-2026-11-23.md` (new)
- `docs/sprints/current.md`
- `docs/STATUS.md`
- `docs/prs/docs-backlog-tidy.md`

## Migrations

- None.

## Risks

- An item judged done from the code alone may still have a gap a user
  would see. Each "done" entry names what was checked.

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`
- `npm --prefix frontend test`: 478 passed (for the count in STATUS).

## Acceptance criteria satisfied

- Every open backlog item is true of the code today, in one list.

## Follow-ups

- Sprint 62 drawn from "Left to finish the current product" and the design
  pass, for the owner to approve.
