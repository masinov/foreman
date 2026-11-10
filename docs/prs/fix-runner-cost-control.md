# PR Summary: fix/runner-cost-control

## Summary

- Sprint 55 slice 3. Makes the per-run cost ceiling real and stops a
  finished run from being thrown away by a gate.

## Scope

- `foreman/runner/claude_code.py`: `--max-budget-usd`; terminal-line
  handling; budget stop mapped to `agent.killed` (cost) with cost, session
  and duration; bounded wait after the stream ends.
- `foreman/runner/process.py`: `close()` kills what is left of an exited
  child's process group.
- `foreman/orchestrator.py`: kill events keep cost and session; per-run
  ceiling is the lower of the role's and `runner_max_cost_usd`; cost limits
  of 0 are off.
- `roles/*.toml`: ceilings (developer 30, architect and frontier reviewer
  10, reviewers 5, triage 2).
- Not in scope: token accounting with cache tokens, Codex cost, SIGHUP and
  parent-death handling (slice 4).

## Files changed

- `foreman/runner/claude_code.py`, `foreman/runner/process.py`,
  `foreman/orchestrator.py`, `roles/*.toml`
- `tests/test_runner_lifecycle.py`, `tests/test_orchestrator.py`,
  `tests/test_roles.py`
- `docs/MANUAL.md`, `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- A developer run that legitimately needs more than $30 is now stopped; it
  resumes its session on the next visit, and the ceiling is a role setting.
- The budget-stop result shape was not exercised against a real run.
- Killing the leftover process group after a normal exit ends any process
  an agent deliberately left running in its own group.

## Tests

- `python -m unittest discover -s tests`: 1019 pass, 1 skipped (8 new,
  five of them with real child processes)
- `ruff check foreman tests scripts`: clean

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Spend on one run is bounded by a ceiling enforced while the agent works.
- An over-ceiling run that finished is recorded as completed with its cost.
- A lingering or forking agent process cannot hold a step or outlive it.

## Follow-ups

- Slice 4: SIGHUP and parent-death signal. Slice 5: lease lifecycle.
