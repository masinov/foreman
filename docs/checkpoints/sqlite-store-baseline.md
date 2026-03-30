# Checkpoint: sqlite-store-baseline

## What works

- `foreman.models` defines typed project, sprint, task, run, and event records
- `foreman.store` bootstraps the spec-aligned SQLite schema and persists each
  core entity type
- `tests/test_store.py` proves round-trip persistence and enforces the single
  active-sprint-per-project constraint
- `foreman projects --db <path>` and `foreman status --db <path>` can inspect
  persisted store data from the installed CLI

## What is incomplete

- `foreman init` still does not create or persist projects
- roles, workflows, scaffold generation, orchestrator logic, and native runners
  remain placeholder modules
- broader CLI inspection surfaces such as `project`, `task list`, `history`,
  `watch`, and `board` do not use the store yet

## Known regressions

- none identified in the validated slice

## Schema or migration notes

- the baseline schema is bootstrapped directly from `foreman.store.SCHEMA_SQL`
- there is no migration framework yet; schema evolution rules should be
  captured in an ADR when later slices depend on them

## Safe branch points

- `feat/sqlite-store-baseline` after store models, CLI `--db` inspection,
  tests, and repo-memory updates
