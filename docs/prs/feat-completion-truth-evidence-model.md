# PR Summary: feat/completion-truth-evidence-model

## Summary

Recover and finish sprint-46 task 1 after the autonomous run stopped on a low
cost cap and exposed a local schema mismatch. This branch lands a first-class
`CompletionEvidence` dataclass and `build_completion_evidence()` method in
`foreman/orchestrator.py`, persists that evidence to `tasks` via
`completion_evidence_json`, repairs additive local schema drift during store
initialization, and raises shipped role and executor cost caps to `$1000.00`
so monthly-plan environments do not stop native runs prematurely.

## Scope

- `foreman/orchestrator.py` — `CompletionEvidence`, evidence scoring, and
  merge-finalization persistence
- `foreman/models.py` — `Task.completion_evidence`
- `foreman/store.py` — evidence serialization plus local schema-drift repair
- `foreman/migrations.py` — migration 5 adds `completion_evidence_json`
- `roles/*.toml` and `foreman/executor.py` — raise default role and runner
  cost caps to `$1000.00`
- `tests/test_orchestrator.py`, `tests/test_migrations.py`,
  `tests/test_roles.py`, `tests/test_executor.py` — regression coverage

## Files changed

- `foreman/orchestrator.py`
- `foreman/models.py`
- `foreman/store.py`
- `foreman/migrations.py`
- `foreman/executor.py`
- `roles/architect.toml`
- `roles/code_reviewer.toml`
- `roles/developer.toml`
- `roles/security_reviewer.toml`
- `tests/test_orchestrator.py`
- `tests/test_migrations.py`
- `tests/test_roles.py`
- `tests/test_executor.py`
- `docs/STATUS.md`
- `docs/sprints/current.md`

## Migrations

- Migration 5: `ALTER TABLE tasks ADD COLUMN completion_evidence_json TEXT NOT NULL DEFAULT ''`
- `ForemanStore.initialize()` also repairs long-lived local databases whose
  migration ledger claims version 5 without the matching column already
  present

## Risks

- completion-evidence scoring is intentionally heuristic in this slice; the
  next sprint-46 tasks still need to turn weak verdicts into actual runtime
  guards
- `Task.completion_evidence` remains typed as `Any` to avoid introducing a
  circular import between `models.py` and `orchestrator.py`
- the schema-repair path is deliberately narrow and only handles the known
  additive drift around `completion_evidence_json`

## Tests

- `./venv/bin/python -m pytest tests/test_roles.py tests/test_executor.py -q`
- `./venv/bin/python -m pytest tests/test_migrations.py tests/test_orchestrator.py -q`
- `./venv/bin/python -m pytest tests/test_store.py tests/test_cli.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Output examples

- `foreman task list foreman --sprint sprint-46-completion-truth-hardening`
  now loads successfully on long-lived local databases that previously crashed
  when the migration ledger and `tasks` table shape diverged

## Acceptance criteria satisfied

- [x] `CompletionEvidence` dataclass in `foreman/orchestrator.py` with
  structured task evidence fields
- [x] `build_completion_evidence()` gathers acceptance criteria, changed files,
  diff stats, agent outputs, and built-in test results
- [x] evidence score and verdict persist through
  `finalize_supervisor_merge()`
- [x] evidence is stored on tasks via `completion_evidence_json`
- [x] `engine.completion_evidence` is emitted during merge finalization
- [x] local databases recover if the migration ledger says version 5 exists
  but the `tasks` column is missing
- [x] shipped role and executor defaults no longer stop native runs at low
  per-run USD caps

## Follow-ups

- `task-backend-guard-for-weak-completions` — wire weak or insufficient
  evidence into a real backend completion guard
- `task-reviewer-prompt-hardening-with-engine-produced-evidence` — pass
  evidence into reviewer prompts
- `task-false-positive-completion-regression-coverage` — cover docs-only and
  tests-only implementation false positives
- `task-completion-truth-contract-docs` — document the evidence model and
  completion-truth contract
