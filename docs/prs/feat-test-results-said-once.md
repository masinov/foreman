# PR Summary: feat/test-results-said-once

## Summary

- After the owner's look at slice 1 (2026-11-23), a test step's result reads
  the same everywhere:
  - **Overview, Steps:** the Test row says the count, as the Activity row
    does: "Passed · 1,221 tests in 1 min 54 s".
  - **Checks, Tests row:** the detail is the sentence the step's log ends
    with, such as "186 tests passed in 2 min 58 s at 6332732". When tests
    failed it says "3 of 186 tests failed (exit code 1) in 12 s at …", then
    lists the failed tests by name: up to 50, then "and N more".
  - The output's last line (the lone "OK") is gone from Checks. The full
    output is in the step's Activity.
- The report reader keeps the names of the failed tests
  (`report.failed_tests`).
- Foreman's own project writes test reports:
  - unittest-xml-reporting is in the dev dependencies, which a task's
    working copy installs;
  - the project's `test_command` was set with `foreman config` on
    2026-11-23 to `python -m xmlrunner … -o "$FOREMAN_TEST_REPORT_DIR"` and
    vitest's JUnit reporter.

## Scope

- **Engine:** `foreman/engine/builtins/test_report.py`.
- **Read side:** `foreman/services/{task_models.py,tasks.py}`.
- **Frontend:**
  - `pages/shared/activityWords.js` (`testRunSentence`);
  - `pages/task/{runWords.js,taskWords.js,ChecksTab.jsx}`;
  - `styles/task.css`.
- `pyproject.toml`.

## Files changed

- As in Scope.
- **Tests:**
  - `tests/test_test_report.py`, `tests/test_builtins.py`,
    `tests/test_dashboard_task_reads.py`;
  - `frontend/src/pages/task/TaskPage.test.jsx`.
- **Docs:**
  - ADR-0035, amended;
  - `docs/design/dashboard-v7/README.md`, `CHANGELOG.md`, this note.

## Migrations

- None.

## Risks

- None beyond slice 1's. A failed test's name is the report's text, shown
  as text.

## Tests

- **Python:** the affected modules, then the whole suite.
- **Frontend:** `npm test` (483), `npm run lint`, `npm run build`.

## Acceptance criteria satisfied

- The Overview's Test row says the count.
- The Checks detail is the log's sentence, names the failed tests, and
  has no "OK".

## Follow-ups

- Assay's test command, once the owner says.
