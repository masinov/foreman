# PR Summary: fix/engine-session-cost-counted-once

## Summary

- Sprint 59, slice 2. A run in a resumed Claude Code session is charged only
  for itself.

## Scope

- What was wrong: the CLI's `total_cost_usd` is the session's running total
  when a session is resumed. The engine stored it as the run's cost, so
  every resume counted the earlier runs again. Seen in Foreman's own
  database: sessions whose recorded costs rise run after run (0.596, 0.717,
  0.828, 1.018, 1.139), and one run that did nothing in 36 ms recorded
  $4.99, the total of the run before it.
- Now: the runner is told what the session had counted before the run
  (`AgentRunConfig.session_cost_baseline_usd`, read from the last run of
  that session) and reports the difference. The total is kept in the new
  column `runs.session_cost_usd`.
- The engine's cost gate works on the run's own share. The CLI is given this
  run's limit on top of what the session carried, so a session that has
  already spent near the limit is not stopped at once.
- An infrastructure retry in the same session carries forward what the
  failed attempt spent.
- A total lower than what was carried means the CLI's count started over
  (three older sessions in the database show this); it is then the run's
  own cost.

## Files changed

- `foreman/runner/base.py`, `foreman/runner/claude_code.py`
- `foreman/engine/agent_step.py`, `foreman/engine/records.py`,
  `foreman/engine/results.py`, `foreman/engine/workflow_runner.py`
- `foreman/models.py`, `foreman/store/runs.py`, `foreman/store/rows.py`,
  `foreman/migrations.py`
- `tests/test_runner_claude.py`, `tests/test_migrations.py`,
  `tests/test_engine_agent_step.py`
- `docs/STATUS.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`

## Migrations

- 24: adds `runs.session_cost_usd`; for Claude Code runs that have a session
  and a cost, keeps the recorded figure as the session total and rewrites
  `cost_usd` as the difference from the previous run of the session. Runs
  with no session, no cost, or another backend are untouched. The reported
  figures remain in each run's `agent.completed` event.

## Risks

- That the total is carried across a resume is inferred from recorded runs
  (CLI 2.1.322), not from the CLI's documentation. If a future CLI reports a
  per-run figure, a run cheaper than what the session carried is read
  correctly (count started over), but a run dearer than that would be
  undercounted by the carried amount.
- Whether the CLI's own budget is counted per session or per run is not
  known. Giving it the carried amount on top is safe either way, because
  the engine's gate enforces the per-run limit.
- Not run against a real agent.

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1352 tests, 5 skipped)
- frontend lint, tests and build (unchanged code)

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A resumed run records its own cost; the migration corrects recorded runs;
  each has a test that fails without the change.

## Follow-ups

- Codex reports no cost; nothing to correct there.
