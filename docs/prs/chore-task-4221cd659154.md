# PR Summary: chore/task-4221cd659154

## Summary

Cache `CompletionEvidence` on the `Task` record on first build and reuse it on subsequent reviewer prompts, avoiding redundant `git diff` and store lookups on repeated renders.

## Scope

- `foreman/models.py` — type annotation on `Task.completion_evidence`
- `foreman/store.py` — reconstruct `CompletionEvidence` from stored JSON dict
- `foreman/orchestrator.py` — cache-on-first-render in `_build_prompt`

## Files changed

- `foreman/models.py`
- `foreman/store.py`
- `foreman/orchestrator.py`
- `docs/prs/chore/task-4221cd659154.md` (new)

## Migrations

- none (no schema change; `completion_evidence_json` column pre-existed)

## Risks

- `CompletionEvidence` is a `frozen=True` dataclass; the reconstructed instance is identical to the original since it is restored from the same serialized form
- `_build_prompt` now calls `store.save_task()` after building evidence for the first time — minor perf cost on cold path, net savings on warm hits

## Tests

- 77 orchestrator tests pass (`./venv/bin/python -m pytest tests/test_orchestrator.py -x -q`)
- All compile checks pass

## Acceptance criteria satisfied

- Evidence is persisted to `Task.completion_evidence` on first build via `_build_prompt`
- Subsequent reviewer prompts read `task.completion_evidence` without recomputing
- Evidence fields are injected into reviewer prompt context: verdict, reasons, score, score_breakdown, criteria counts, changed files, diff stat, builtin test result
- Store deserializes `CompletionEvidence` from JSON in `_row_to_task`

## Follow-ups

- Expose `completion_evidence` fields in the reviewer role TOML templates so agents can read them explicitly
- Consider invalidating cached evidence when a task gets new runs (add a `evidence_built_for_run_id` field)
