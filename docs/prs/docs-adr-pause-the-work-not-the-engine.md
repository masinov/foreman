# PR Summary: docs/adr-pause-the-work-not-the-engine

## Summary

- Proposes ADR-0043: a user pauses the work (workspace, sprint or task), not
  an engine. Pause lets the running step finish; Stop cuts it now; both end
  paused; Resume releases everything at and below its level, so no Resume
  does nothing. Start sprint is the only way a sprint starts; Run next only
  orders; a task a user stops is paused, not blocked. The engine leaves the
  page; the program is a worker, with Start worker only on a fault line.
- Pauses become rows in a `pauses` table that workers read at their
  existing poll sites; `pause`, `resume` and `stop_task` leave the command
  table.

## Scope

The ADR, the ADR index and this note. No code. The design README changes
listed in the ADR land with the dashboard slice, once the ADR is accepted.

## Files changed

- `docs/adr/ADR-0043-the-work-is-paused-not-the-engine.md`
- `docs/adr/README.md`
- this note.

## Migrations

None here. The ADR plans one (`pauses`).

## Risks

None until built. The ADR's own risks are in its Consequences.

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`

## Acceptance criteria satisfied

- The model chosen by the owner on 2026-11-25, with the resume rule they
  asked for, written as a decision the code can follow.

## Follow-ups

- The three slices in the ADR's "Order of work".
