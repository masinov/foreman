# PR Summary: fix/runner-quota-exhaustion

## Summary

Sprint 54 live-run fix F2, found during the first resident run. Fifty-six
seconds into a develop step the Claude subscription's five-hour usage window
ran out: the CLI streamed a `rate_limit_event` with `status: rejected` and
`resetsAt`, then an error result reading "You've hit your session limit ·
resets 3:20pm". The runner surfaced it as a plain `agent.error`, the step
outcome became `error`, the workflow had no transition for it, and the task
was blocked with the quota text as its reason, `failure_type` null. The
resident engine then idled, logging two INFO lines every five seconds.

Quota exhaustion is an infrastructure condition with a known reset time, not
a task defect. This branch makes the engine treat it that way end to end.

## Scope

- **Runner** (`foreman/runner/base.py`, `claude_code.py`):
  `QuotaExhaustedError(InfrastructureError)` with `retry_after` (ISO 8601
  UTC) and the charged `payload`. The Claude runner remembers the last
  `agent.rate_limit` notice and raises the error when an error result
  follows a non-allowed notice or matches the limit wording; the reset time
  comes from the notice's `resets_at`. `run_with_retry` yields one
  `agent.error` with `quota_exhausted` and `retry_after` and does not retry.
- **Orchestrator** (`foreman/orchestrator.py`): `AgentExecutionResult` and
  `Run` carry `failure_type` (`quota`, `preflight`, `infrastructure`,
  `agent`) and `retry_after`. A quota failure skips the output-contract
  retry, persists the task's resume point (`workflow_current_step`, carried
  output) with status `in_progress`, refunds the step visit, emits
  `engine.quota_exhausted`, releases the task lease, and raises
  `QuotaPauseError`, which `run_project` turns into
  `ProjectRunResult(stop_reason="quota_exhausted", retry_after=…)`.
- **Resident engine** (`foreman/serve.py`): on `quota_exhausted` the loop
  waits until the reset (`quota_wait_seconds`: reported time plus a grace
  period, clamped to one minute to six hours, fifteen minutes when unknown)
  and resumes without maintenance; `--once` exits 0. Idle is narrated once
  at INFO; repeated empty passes log at DEBUG.
- **CLI** (`foreman run`): prints the reset time and exits 75
  (`EX_TEMPFAIL`) on a quota stop.
- **Docs**: `docs/MANUAL.md` (quota section, event taxonomy, exit codes),
  `CHANGELOG.md`, `docs/STATUS.md`, `docs/sprints/current.md`, live-run notes.

## Files changed

- `foreman/runner/base.py`, `foreman/runner/__init__.py`,
  `foreman/runner/claude_code.py`, `foreman/orchestrator.py`,
  `foreman/serve.py`, `foreman/cli.py`
- `tests/test_runner_claude.py` (+3), `tests/test_runner.py` (+1),
  `tests/test_quota_pause.py` (new, 2), `tests/test_serve.py` (+4)
- `docs/MANUAL.md`, `CHANGELOG.md`, `docs/STATUS.md`,
  `docs/sprints/current.md`, `docs/reviews/sprint-54-live-run-notes.md`,
  `docs/prs/fix-runner-quota-exhaustion.md`

## Migrations

- none (`runs.failure_type` already existed and was never written)

## Risks

- The quota wording match is a regular expression over the error text as a
  fallback for backends that send no rate-limit notice; an unrelated error
  mentioning "quota" would pause instead of block. The pause is bounded and
  the task stays resumable, so the failure mode is a delay, not a loss.
- A resident engine waiting on a reset holds the project lock; a `foreman
  run` during the wait is refused as before. The command table (slice 2a)
  will let an operator interrupt the wait.
- The Codex runner does not classify quota errors yet.

## Tests

- `./venv/bin/python -m unittest discover -s tests` — full suite green
  (count in the merge commit).
- `scripts/validate_repo_memory.py` clean; `git diff --check` clean.

## Screenshots or output examples

```
Stop reason: quota_exhausted
Retry after: 2026-09-04T13:20:00Z
The paused task keeps its resume point; run again once the backend quota resets.
```

## Acceptance criteria satisfied

- a quota failure never blocks a task or spends its loop budget,
- the run records why it failed and when to retry,
- the resident engine resumes on its own after the reset,
- idle logging is bounded.

## Follow-ups

- `foreman engine` commands (slice 2a) to interrupt a quota wait.
- Codex runner quota classification.
