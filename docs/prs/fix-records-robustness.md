# PR Summary: fix/records-robustness

## Summary

These are faults an independent review found in FOR-61 and FOR-62 (step
records and the reviewer's verdict), before their code went live. Sprint
63's own reviews had approved in seconds. Each is recorded in the ADR-0042
amendment of 2026-11-25.

1. **Quoted blocks.** The last record block that is a JSON object counts,
   so a quoted example after the record no longer fails the step. Windows
   line endings are read.
2. **Choices** are matched without regard to case and stored as declared,
   for example `s2` is read as `S2`.
3. **The format example** shows S4 and `judgement`, never S1.
4. **The missing-marker retry** asks for the record and the marker.
5. **An approval must list the task's criteria** when the task has any.
6. **Deny and steer** hand the developer their S1 and S2 findings, after the
   reason.
7. **A `developer_report` of another shape** in a project's own role is left
   out of prompts instead of raising.

## Scope

The record reader, the verdict check, the retry text, the report text, the
agent step's tally, tests, ADR-0042, the sprint file.

## Files changed

- `foreman/definitions/records.py`
- `foreman/engine/verdict.py`
- `foreman/engine/output_contract.py`
- `foreman/engine/agent_step.py`
- `foreman/engine/report_words.py`
- `tests/test_step_records.py`
- `tests/test_review_verdict.py`
- `tests/engine_support.py`
- `docs/adr/ADR-0042-a-role-returns-its-record-in-a-fenced-block.md`
- `docs/sprints/current.md`
- this note.

## Migrations

None.

## Risks

- A reviewer that approves without listing criteria on a task that has
  them now gets one correction and then an error.

## Tests

- New tests:
  - a quoted block after the record;
  - CRLF;
  - the missing-marker retry asks for the record;
  - another shape of report;
  - an approval with no criteria listed, with and without task criteria;
  - lower-case severities;
  - the example shows no blocking finding;
  - deny and steer carry their findings.
- Whole Python suite: 1,765 passed. ruff and lint-imports are clean.

## Acceptance criteria

- Each finding above is fixed, with a test.

## Follow-ups

- Compare the verdict's criteria entries with the task's own text.
- A project's own reviewer that uses `{previous_output}` sees only the
  developer's words outside the record. Recorded in the backlog.
