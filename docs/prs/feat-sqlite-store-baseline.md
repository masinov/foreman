# PR Summary: feat/sqlite-store-baseline

## Summary

- implement the first SQLite-backed Foreman store slice
- add typed models for projects, sprints, tasks, runs, and events
- expose a narrow store-backed inspection path through `foreman projects --db`
  and `foreman status --db`

## Scope

- replace the placeholder `foreman.models` and `foreman.store` modules with a
  spec-aligned baseline
- extend the CLI just enough to inspect a real database without expanding into
  project creation or orchestration
- add store round-trip coverage and refresh repo-memory docs to point at the
  next slice

## Files changed

- `foreman/models.py`
- `foreman/store.py`
- `foreman/cli.py`
- `tests/test_store.py`
- `tests/test_cli.py`
- `README.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `CHANGELOG.md`
- `docs/checkpoints/sqlite-store-baseline.md`

## Migrations

- bootstrap DDL only; no migration framework yet

## Risks

- the schema is currently defined inline in `foreman.store`, so future schema
  evolution still needs an ADR and migration strategy
- only `projects` and `status` can inspect the store through the CLI today; the
  rest of the command surface remains stubbed

## Tests

- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`
- `./venv/bin/foreman --help`
- `./venv/bin/foreman projects`
- `./venv/bin/foreman status`

## Screenshots or output examples

- `foreman projects --db <path>` lists seeded projects with active sprint and
  task counts
- `foreman status --db <path>` reports project count, active sprint count, and
  task totals by status

## Acceptance criteria satisfied

- typed models exist for the core SQLite entities
- the SQLite schema can be bootstrapped idempotently
- project, sprint, task, run, and event rows round-trip through the store
- repo-memory docs now point the next agent at role and workflow loading

## Follow-ups

- implement TOML role and workflow loading with validation
- persist projects through `foreman init`
- expand store-backed CLI inspection beyond `projects` and `status`
