# docs/task-adr-and-spec-6-3-the-engine-finishes-a-sprint-on

## Summary

Sprint 60b. Records the owner's decision of 2026-11-16 before the code
changes: the engine finishes a sprint only in an autonomous project.

## Scope

- ADR-0025 (accepted), listed in `docs/adr/README.md` (ADR-0024 was missing
  from that table and is added).
- Spec §6.3 says, level by level, who completes a resolved sprint; a task
  added to a resolved, still active sprint is run; a blocked task prevents
  completion at every level. §6.4 says its actions follow the sprint being
  finished, by the engine or by a person.
- `docs/STATUS.md` and `CHANGELOG.md` note the revision.

## Files changed

`docs/` and `CHANGELOG.md` only.

## Migrations

None.

## Risks

Until the next sprint 60b task lands, the code still completes a resolved
sprint at every level; recorded in `docs/STATUS.md`.

## Tests

`./venv/bin/python scripts/validate_repo_memory.py`.

## Acceptance criteria satisfied

All listed on the task; nothing under `foreman/`, `frontend/` or `tests/`
changed.

## Follow-ups

The code task: a resolved sprint stays active in a directed or supervised
project.
