# PR Summary: feat/test-report-count

## Summary

- Sprint 62 opens: "finish what's there" (`docs/sprints/current.md`).
- Slice 1: Foreman counts the tests (ADR-0035).
  - The test step names a fresh, empty directory in
    `FOREMAN_TEST_REPORT_DIR`. The directory is outside the working copy and
    is removed afterwards. A test command that writes JUnit XML there tells
    Foreman how many tests ran.
  - The Steps table and the step's facts say "Passed · 1,599 tests, 1
    skipped".
  - The step's story says "1,599 tests passed (1 skipped) in 4 min 34 s at
    abc1234".
  - The Checks tab's Tests row says the count, and drops the output's last
    line (the lone "OK") when a report counted the tests.
- A built-in step's records are saved as they happen. The test step's
  start is when the tests started, and their output can be followed while
  they run.

## Scope

- **Engine:**
  - `foreman/engine/builtins/test_report.py` (new) reads the reports.
  - `run_tests.py` names the directory and records `report` and
    `report_problems` on `engine.test_run`.
  - `workflow_runner/builtin_steps.py` passes the event recorder.
- **Read side:**
  - `store/runs.py` returns the run's report beside its commit.
  - `services/task_models.py` has `TestCounts`, `TestsFact.counts` and
    `RunItem.tests`.
  - `services/task_reads.py` and `domain/activity.py` (`STEP_REPORT_EVENT`)
    serve them.
  - `cli/common.py` prints the counts.
- **Frontend:**
  - `testCountWords` and `stepOutcome` in `pages/shared/activityWords.js`;
  - the story line in `pages/task/runWords.js`;
  - `testsWords` in `taskWords.js` and the row in `ChecksTab.jsx`;
  - `formatCount` in `ui/format.js`;
  - the test command's hint in Settings.
- Not in this slice: Foreman's and Assay's own test commands still write
  no report. Both use Python's unittest, which needs unittest-xml-reporting
  installed. Installing it was blocked in this session and is left to the
  owner.

## Files changed

- `foreman/engine/builtins/{test_report.py,run_tests.py}`
- `foreman/engine/workflow_runner/builtin_steps.py`
- `foreman/store/runs.py`, `foreman/domain/activity.py`
- `foreman/services/{task_models.py,task_reads.py}`
- `foreman/cli/common.py`
- `frontend/src/pages/shared/activityWords.js`
- `frontend/src/pages/task/{runWords.js,taskWords.js,ChecksTab.jsx}`
- `frontend/src/pages/settings/GeneralTab.jsx`
- `frontend/src/ui/format.js`
- **Tests:**
  - `tests/test_test_report.py` (new), `tests/test_builtins.py`;
  - `tests/test_dashboard_task_reads.py`, `tests/test_workflow_gates.py`;
  - `frontend/src/pages/shared/activityWords.test.js`,
    `frontend/src/pages/task/TaskPage.test.jsx`.
- **Docs:**
  - `docs/adr/ADR-0035-tests-are-counted-from-junit-reports.md`,
    `docs/adr/README.md`;
  - `docs/MANUAL.md`, `docs/design/dashboard-v7/README.md`;
  - `docs/sprints/{current,backlog}.md`, `CHANGELOG.md`.

## Migrations

- None. The counts are a new field in an event's payload. Earlier test runs
  have none and read as before.

## Risks

- **More writes while tests run.** A test run writes one record per output
  line while it runs, not all of them at its end. The number of records is
  the same as before.
- **Reports are written by the project's own command,** which an agent can
  change. A report can claim any count. The count is shown as what the
  report says: it is a fact about the report, and the exit code still
  decides pass or fail.
- **Old XML parser.** The machine's expat (2.2.9) does not limit entity
  expansion, so a report that declares a document type or an entity is
  refused before parsing.

## Tests

- **Python:** `tests.test_test_report`, `tests.test_builtins`,
  `tests.test_dashboard_task_reads`, `tests.test_workflow_gates`, then the
  whole suite.
  - The new timing test fails without the change to `builtin_steps.py`.
- **Frontend:** `npm test`, `npm run lint`, `npm run build`.
- **A real vitest report** (`--reporter=junit
  --outputFile.junit="$DIR/vitest.xml"`) was read back as 12 tests.

## Acceptance criteria satisfied

- A test step whose command writes a JUnit report reads "Passed · N tests"
  in the table and the facts, and its story says the count.
- The Checks tab says the count instead of the lone "OK".
- The test step's start record is saved when the tests start.

## Follow-ups

- Install unittest-xml-reporting and change Foreman's and Assay's test
  commands to write reports.
- Owner direction 5 reads each test's result from the same reports.
