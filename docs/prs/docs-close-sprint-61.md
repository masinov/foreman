# PR Summary: docs/close-sprint-61

## Summary

- Sprint 61 ("the core, proven", stage 1 of the roadmap) is closed. Slice 6
  is recorded: Assay's sprint 2 ran through Foreman with nobody stepping in,
  8 of 8 merged. Slice 7 is the checkpoint and archive.

## Scope

- Docs only.

## Files changed

- `docs/sprints/archive/sprint-61-the-core-proven.md` (new): the sprint with
  "What slice 6 showed".
- `docs/checkpoints/2026-11-20-sprint-61-closed.md` (new).
- `docs/sprints/current.md`: no sprint open; next is stage 2, starting with
  the identity ADR.
- `docs/STATUS.md`, `docs/ROADMAP.md`, `CHANGELOG.md`.

## Migrations

- none

## Risks

- none; no code changes.

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`

## Screenshots or output examples

- `foreman outcomes assay --sprint sprint-sprint-2-weight-of-evidence-and-first-deployment`:
  8 started, 8 merged; 7 of 8 first time; 1 send-back (review); $2.92 in
  all, $0.36 per merged task; median 6.9 min to merge.

## Acceptance criteria satisfied

- Slice 6: a sprint planned by the project's manager, confirmed by the
  owner, run unattended, what went wrong recorded (nothing in Foreman).
- Slice 7: checkpoint and archive written.

## Follow-ups

- Stage 2: the identity ADR, for the owner to read before code.
- The outcome numbers' place on the dashboard (owner).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
