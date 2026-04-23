## Summary

Retry malformed developer and reviewer outputs once before blocking the task.

## Scope

- detect developer responses that completed normally but omitted `TASK_COMPLETE`
- detect reviewer responses that completed normally but did not parse to
  `APPROVE`, `DENY: ...`, or `STEER: ...`
- append a minimal corrective prompt and rerun the same workflow step once
- emit `engine.output_contract_retry` so the recovery is visible in SQLite

## Files changed

- `foreman/orchestrator.py`
- `tests/test_orchestrator.py`
- `docs/STATUS.md`

## Migrations

- none

## Risks

- this only retries explicit malformed-output cases where the run itself
  completed; infrastructure failures and real agent errors still block as before
- role prompts are still the primary contract; this patch is a recovery path,
  not a substitute for better prompt compliance

## Tests

- `./venv/bin/python -m pytest tests/test_orchestrator.py -q -k 'retries_developer_once_after_missing_completion_marker or retries_reviewer_once_after_malformed_decision_output'`
- `./venv/bin/python -m pytest tests/test_orchestrator.py -q`
- `./venv/bin/python -m py_compile foreman/orchestrator.py`

## Acceptance criteria satisfied

- malformed developer output missing `TASK_COMPLETE` is retried once
- malformed reviewer output is retried once with explicit output-shape instructions
- successful corrective retries let the task continue normally
- second failures still block through the normal workflow path

## Follow-ups

- rerun the remaining sprint-46 tasks against this retry path
- consider similar corrective retries for security-review roles if live runs show
  the same malformed-output behavior there
