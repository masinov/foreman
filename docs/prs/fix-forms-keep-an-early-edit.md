# fix/forms-keep-an-early-edit

## Summary

CI's frontend job failed at `a963ac4` on a settings test that had failed
now and then before ("never sends a host-level setting": the edit was made,
Save was pressed, nothing was sent). The failure could not be reproduced
locally, including under load and with each reply delayed in turn.

The likely cause, from reading the code: the General form reset its draft
in an effect keyed on the values read. An effect also runs once after the
first render, later than the render itself; an edit made in between was
followed by the reset, leaving nothing to save. The task's Overrides form
filled its fields the same way.

## Scope

Both forms now take their starting values when they are first rendered and
start over, while rendering, only when different values are read. No
behaviour a person sees changes.

## Files changed

`frontend/src/pages/settings/GeneralTab.jsx`,
`frontend/src/pages/task/Overrides.jsx`, `CHANGELOG.md`.

## Migrations

None.

## Risks

The cause is inferred, not reproduced. If the test fails again the cause is
elsewhere; the test names the spot (`ProjectSettings.test.jsx`, "never sends
a host-level setting").

## Tests

`ruff`, the Python suite, frontend lint, tests (run six times) and build.

## Follow-ups

None.
