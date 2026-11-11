# chore/package-data

## Summary

Sprint 57 slice 7. What Foreman ships with is inside the package, and the
version has one source.

## Scope

- `roles/`, `workflows/`, `templates/` moved to `foreman/data/`.
  `foreman.data` exposes `ROLES_DIR`, `WORKFLOWS_DIR`, `TEMPLATES_DIR`;
  `default_roles_dir`, `default_workflows_dir` and the scaffold use them.
- `pyproject.toml`: the three directories are package data; `version` is
  dynamic, read from `foreman.__version__`. The API title version reads the
  same attribute.
- Docs name the new paths.

## Files changed

`foreman/data/` (moved files plus `__init__.py`), `foreman/roles.py`,
`foreman/workflows.py`, `foreman/scaffold.py`, `foreman/dashboard/app.py`,
`pyproject.toml`, `tests/test_packaging.py` (new), README, manual,
architecture, changelog, sprint.

## Migrations

None. Role files are edited at `foreman/data/roles/*.toml` from now on.

## Risks

Anyone with a local, uncommitted edit under the old `roles/` directory
keeps it as an untracked file that Foreman no longer reads.

## Tests

Full Python suite and `ruff check`. A wheel was built, unpacked, and run
from outside the repository: it loaded 7 roles and 4 workflows and
`foreman roles` printed them from inside the unpacked package.

## Acceptance criteria satisfied

Slice 7 as written in `docs/sprints/current.md`.

## Follow-ups

The frontend's `package.json` carries its own version; it is not published,
so it is left alone.
