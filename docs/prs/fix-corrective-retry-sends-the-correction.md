# PR Summary: fix/corrective-retry-sends-the-correction

## Summary

- A corrective retry that resumes the agent's session sends the correction
  alone; with no session to resume it sends the first prompt and the
  correction, as before.

## Scope

- `foreman/engine/output_contract.py` (`with_retry_instruction(...,
  resumes_session=)`), `foreman/engine/workflow_runner/agent_steps.py`.

## Files changed

- The two above, `tests/test_engine_agent_step.py`,
  `tests/test_output_contract.py`, MANUAL, CHANGELOG, backlog, sprint file.

## Migrations

- none

## Risks

- Both backends resume a session by id (`claude --resume`, Codex
  `thread/resume`), so the correction lands in a session that holds the
  task.

## Tests

- `test_a_corrective_retry_in_the_same_session_does_not_send_the_task_again`
  fails when the whole prompt is sent again and passes with the change.
- `test_a_retry_that_resumes_the_session_sends_the_correction_alone`.
- Full suite, ruff, `lint-imports`.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The retry sends the correction rather than the first prompt again.

## Follow-ups

- The other two items of slice 3.
