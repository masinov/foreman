# PR Summary: docs/adr-pause-the-work-not-the-engine

## Summary

- Accepts ADR-0043: a user holds the work, not an engine. Two holds:
  **Pause**, soft and per task (on a sprint or the workspace it pauses each
  task, as a torrent client's Pause all does, and any task can be resumed
  alone), and **Block**, hard and with a reason, on a task, a sprint or the
  workspace (nothing under it runs until Unblock). **Stop** cuts the
  running step now and pauses. A hold holds everything downstream, so a
  held sprint neither finishes nor starts the next; otherwise Foreman
  finishes and starts sprints itself where the project lets it.
- Start sprint replaces Activate; Run next only orders; a task a user stops
  is paused, not blocked. The engine leaves the page; the program is a
  worker, with Start worker only when none runs. No names in status lines,
  toasts or buttons.
- Pauses are fields on tasks, sprint and workspace blocks are rows in
  `holds`, and workers read them at their existing poll sites; `pause`,
  `resume` and `stop_task` leave the command table.
- Shaped by the owner's review, a second opinion (Fable 5.2) and a survey
  of how print queues, workflow engines, CI queues and torrent clients
  handle pausing.

## Scope

The ADR, the ADR index and this note. No code. The design README changes
listed in the ADR land with the dashboard slice, once the ADR is accepted.

## Files changed

- `docs/adr/ADR-0043-the-work-is-paused-not-the-engine.md`
- `docs/adr/README.md`
- `docs/sprints/backlog.md` (owner direction 10, dependencies across sprints)
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
