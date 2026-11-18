# PR Summary: fix/new-project-defaults

## Summary

- Found on Assay, which had to be fixed by hand:
  - a new project's workers ran on `claude-sonnet-4-6`, an old id;
  - a new project had no merge policy, so the built-in `auto` merged into
    `main` without a person.
- A project added from the dashboard had no settings at all.

## Scope

- `foreman/scaffold.py`: `DEFAULT_DEFAULT_MODEL` is `claude-sonnet-5-5`;
  `NEW_PROJECT_POLICY` and `new_project_settings()` added.
- `foreman init` (new projects only) and `DashboardService.create_project`
  use `new_project_settings()`.

## Files changed

- `foreman/scaffold.py`, `foreman/cli/projects.py`, `foreman/dashboard_service.py`
- tests: `tests/test_scaffold.py`, `tests/test_cli.py`, `tests/test_dashboard_safety.py`
- `docs/MANUAL.md`, `CHANGELOG.md`

## Migrations

- none. Existing projects keep their settings.

## Risks

- none known. The matrix's built-in default is unchanged, so projects that
  never set `merge_approval` behave as before.

## Tests

- ruff, the full Python suite.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A project made by `foreman init` or from the dashboard has
  `merge_approval = human` and a default model the dashboard offers. A test
  ties the default to the dashboard's model list.

## Follow-ups

- none
