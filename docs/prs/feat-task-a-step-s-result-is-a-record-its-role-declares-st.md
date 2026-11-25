# PR Summary: feat/task-a-step-s-result-is-a-record-its-role-declares-st

## Summary

- A role can declare the record its step returns (`[completion.record]`: a kind
  and named fields, each required or not). The agent returns it as a fenced
  `foreman-record` JSON block in its final message (ADR-0042). Foreman checks it,
  stores it with the run and returns it with the task's runs.
- The shipped developer declares the developer's report (ADR-0040): what changed
  and why, each acceptance criterion with how it was verified and whether it was,
  what was not verified, behaviour changed beyond the task, docs touched,
  follow-ups filed.
- The code, security, triage and frontier reviewers' prompts show that report as
  sections. The task page shows it in the develop step's details.

## Scope

- ADR-0040 build item 2, first half, and ADR-0041 section 2.
- Not in scope: the reviewer's verdict record (next task); comparing the report's
  criteria with the task's own list.

## Files changed

- `foreman/definitions/records.py` (new), `foreman/definitions/roles.py`
- `foreman/engine/output_contract.py`, `agent_step.py`, `results.py`,
  `prompts.py`, `report_words.py` (new), `workflow_runner/agent_steps.py`
- `foreman/store/migrations.py`, `rows.py`, `runs.py`; `foreman/domain/models.py`;
  `foreman/history/records.py`
- `foreman/services/task_models.py`, `task_reads.py`, `tasks.py`,
  `definition_forms.py`
- `foreman/data/roles/*.toml` (developer declares the report; reviewers take it)
- `frontend/src/pages/task/DeveloperReport.jsx`, `ActivityTab.jsx`,
  `styles/task.css`
- `docs/adr/ADR-0042-...`, `docs/adr/README.md`, `docs/ARCHITECTURE.md`
- Tests: `tests/test_step_records.py`, `DeveloperReport.test.jsx`,
  `TaskPage.test.jsx`; scripted developers in other tests end with a report.

## Migrations

- 30: `runs.record_json TEXT` (NULL for every earlier run and for roles with no record).

## Risks

- The shipped developer now needs a valid report: a developer that omits it gets
  one corrective retry, then the step is an error. A project's own developer role
  stored in the database keeps its old prompt and declares no record, so it is
  unaffected.
- Existing tests that script the shipped developer through the native runner now
  end their message with a report (`DEV_REPORT` in `tests/engine_support.py`); one
  heading assertion says "Developer's Report"; the migration-29 test seeds its
  runs by raw SQL because the store writes migration 30's column.
- Reviewers see the report instead of the developer's free text.

## Tests

- `./venv/bin/python -m pytest tests -n auto -q`: all pass.
- `npx vitest run` and `npx eslint . --max-warnings 0` in `frontend/`.

## Screenshots or output examples

- n/a: not opened in a browser here; the frontend tests cover the page.

## Acceptance criteria satisfied

- Loader validates and rejects a malformed declaration: `DeclarationTests`.
- Report stored with the run and returned by the API: `EngineRecordTests`.
- Missing or malformed report is `error`, with the reason in the run: `EngineRecordTests`, `ReadingTests`.
- Code reviewer's prompt shows the report criterion by criterion: `EngineRecordTests`.
- A role without a record works as before: `ReadingTests`, the existing suite.
- Task page shows the report: `DeveloperReport.test.jsx`, `TaskPage.test.jsx`.
- ADR-0042.

## Follow-ups

- Compare the report's `criteria` with the task's acceptance criteria.
- Show a record on the agent side bar's step as well as the Activity tab.
