# PR Summary: feat/finish-sprints-setting

## Summary

- Sprint 60, decision 5: "Finish sprints: A person / Foreman" in Project
  settings, Who decides, beside "Approve merges" (ADR-0025 amendment).

## Scope

- `ProjectSettings.sprint_completion` (`human` by default, or `auto`),
  validated. `SprintFlow.resolve` finishes a resolved sprint and starts the
  next only when it is `auto`.
- The autonomy level no longer decides it. Nothing could set it to
  `autonomous`, and both projects in the database are `supervised`, so no
  project changes behaviour.
- The settings page shows the choice. The effective settings already carry
  every field, so the API needed no change.
- Docs: ADR-0025 amendment, MANUAL (the sprint lifecycle and the settings
  table), ARCHITECTURE, the STATUS conflict note against spec 6.3.

## Migrations

- none

## Tests

- sprint flow tests set `sprint_completion` instead of the autonomy level,
  plus a new test that an `autonomous` level alone finishes nothing; a
  settings validation test; a settings page test. The full suites.
