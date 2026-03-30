# Checkpoint: context-projection-runtime

## What works

- Foreman projects runtime `.foreman/context.md` and `.foreman/status.md`
  directly from SQLite state
- the orchestrator refreshes runtime context before agent steps and after task
  completion
- `_builtin:context_write` reuses the same projection path for explicit
  workflow-driven context refreshes

## What is incomplete

- `foreman approve` and `foreman deny` do not exist yet
- native Claude Code and Codex runner backends are still pending
- open decisions are not yet persisted in SQLite, so status projection uses a
  placeholder

## Known regressions

- none known from the context projection slice itself

## Schema or migration notes

- no schema migration was required
- runtime status projection currently derives completed sprint summaries from
  persisted task titles because the schema does not yet store richer
  deliverable records

## Safe branch points

- `feat/context-projection-runtime` after context, orchestrator, and full
  unittest validation pass
- repo memory rolled forward to `sprint-05-human-gates`
