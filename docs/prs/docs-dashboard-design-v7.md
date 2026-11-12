# docs/dashboard-design-v7

## Summary

Sprint 58 slice 0. The dashboard design agreed with the owner on 2026-11-12
is in the repository and is the UI reference. Sprint 58 (frontend rebuild,
run through Foreman) is opened; sprint 57 is archived.

## Scope

- `docs/design/dashboard-v7/`: 17 standalone screens and a `README.md` with
  the structure, the tokens, the line and list rules, the wording and the
  motion.
- ADR-0020: the design is the reference; how the frontend is laid out,
  routed, fed and tested; the temporary `/dashboard/legacy` seam; what the
  API must add.
- `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md`,
  `docs/TESTING.md` point to the design. `docs/mockups/foreman-mockup-v6.html`
  stays as history.
- `docs/STATUS.md` records the change of authority and the backlog/intake
  mismatch.
- `docs/sprints/current.md` is sprint 58; sprint 57 is archived with slice 9
  moved to the backlog as an open decision.
- The repository validator requires `docs/design/dashboard-v7/README.md`.

## Files changed

Docs, one line in `scripts/repo_validation.py`.

## Migrations

None.

## Risks

`AGENTS.md` now tells agents to follow the new design. This rests on the
owner's statement that the base is ready for implementation; reverting is
one commit.

## Tests

Repository validator and the Python suite.

## Acceptance criteria satisfied

A fresh agent can find the design, its rules and the sprint plan without
chat history.

## Follow-ups

Sprint 58 slices 1 to 13.
