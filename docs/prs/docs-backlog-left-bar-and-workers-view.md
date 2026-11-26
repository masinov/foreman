# PR Summary: docs/backlog-left-bar-and-workers-view

## Summary

- Records the owner's direction of 2026-11-26 for the views (backlog,
  direction 6): every view is an entry of a menu down the left side, with a
  submenu under the chosen view; whether the breadcrumb stays is decided
  with it.
- The Workers view of ADR-0043 is part of the machines view of that set,
  not a settings page; ADR-0043 says so.

## Scope

Docs only.

## Files changed

- `docs/sprints/backlog.md`
- `docs/adr/ADR-0043-the-work-is-paused-not-the-engine.md`
- this note.

## Migrations

- none

## Risks

- none

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The owner's words are in the backlog where the views are designed.

## Follow-ups

- The design reference for the views (roadmap stage 5).
