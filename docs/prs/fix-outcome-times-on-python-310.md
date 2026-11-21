# PR Summary: fix/outcome-times-on-python-310

## Summary

- CI's Python 3.10 job failed on `3f70b1e` (slice 3 of the activity work).
  `datetime.fromisoformat` in Python 3.10 does not read a trailing `Z`,
  which the store writes, so `outcome_numbers._when` returned nothing. A
  merge milestone's minutes were empty there, and so were ADR-0034's median
  wait and median time to merge since they landed. The live dashboard runs
  3.12 and was not affected.

## Scope

- `_when` reads `...Z` as `+00:00`.

## Files changed

- `foreman/domain/outcome_numbers.py`, `tests/test_outcome_numbers.py`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- none

## Tests

- On a Python 3.10 environment: the milestone test fails without the fix
  and passes with it; a new test reads `Z` times. The full suite on 3.10
  passes but for `test_cli`'s smoke class, which installs into a `./venv`
  the scratch copy did not have. CI runs both versions.

## Acceptance criteria satisfied

- CI green on both Python versions.

## Follow-ups

- none

🤖 Generated with [Claude Code](https://claude.com/claude-code)
