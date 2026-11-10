# PR Summary: feat/token-usage-breakdown

## Summary

- Token usage is stored and shown as input, output, cache read and cache
  creation instead of one number that left the cache out.

## Scope

- `TokenUsage` model and four columns on `runs` (migration 19).
- Claude runner reads the split from the result line's `usage`.
- Orchestrator carries it to the run; store sums it in totals.
- API: `token_usage` on runs and on project, sprint and task totals.
- CLI: `foreman cost` and `foreman history`.
- Dashboard: task drawer, run history, sprint footer.
- `token_count` keeps its meaning (fresh input plus output).

## Files changed

- `foreman/models.py`, `foreman/migrations.py`, `foreman/store.py`,
  `foreman/runner/claude_code.py`, `foreman/orchestrator.py`,
  `foreman/dashboard_service.py`, `foreman/cli.py`
- `frontend/src/format.js`, `frontend/src/components.jsx`,
  `frontend/src/App.jsx`, `foreman/dashboard_frontend_dist/*`
- `tests/test_store.py`, `tests/test_runner_lifecycle.py`,
  `frontend/src/format.test.js`
- `docs/MANUAL.md`, `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- 19: `runs.input_tokens`, `output_tokens`, `cache_read_tokens`,
  `cache_creation_tokens` (integer, default 0). Applied cleanly to a copy of
  the live database at version 18.

## Risks

- Older runs have no split; the dashboard shows the old total for them.
- Code older than this branch cannot write runs to a migrated database
  only if it lists columns positionally; it does not (named columns).

## Tests

- `python -m unittest discover -s tests`: 1025 pass, 1 skipped (3 new)
- `npm --prefix frontend test`: 53 pass (2 new); build clean
- `ruff check foreman tests scripts`: clean

## Screenshots or output examples

- `Token split: in=… | out=… | cache_read=… | cache_write=…` in
  `foreman cost` once a run has reported usage.

## Acceptance criteria satisfied

- A run's four token figures survive from the backend's result line to the
  database, the API, the CLI and the dashboard.

## Follow-ups

- Codex split when Codex work resumes.
