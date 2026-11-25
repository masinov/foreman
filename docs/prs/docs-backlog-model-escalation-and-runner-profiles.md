# PR Summary: docs/backlog-model-escalation-and-runner-profiles

## Summary

- Records the owner's decision of 2026-11-25 on choosing models: the size
  label (`complexity`) goes; a model is pinned per task with the existing
  override; a step moves up the role's ladder only after failures of its
  own work (`escalate_after`, default 2), not on restarts or conflict
  refreshes; each move up is in the Activity with its reason. A sprint 64
  candidate, under "Found while reviewing sprint 63".
- Adds owner direction 9: user-defined runner profiles (harness, model,
  endpoint) and ladders chosen by the fixed facts of ADR-0041, with
  handoffs carried by step records. For the future.

## Scope

`docs/sprints/backlog.md` and this note. No code.

## Files changed

- `docs/sprints/backlog.md`
- this note.

## Migrations

None.

## Risks

None.

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`

## Acceptance criteria satisfied

- The decision and the direction are in the backlog, with the owner's
  words.

## Follow-ups

- Build the escalation rule in sprint 64, with its ADR-0041 amendment.
