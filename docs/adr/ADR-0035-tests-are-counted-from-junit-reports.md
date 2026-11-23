# ADR-0035: Tests Are Counted From JUnit Reports

- **Status:** accepted
- **Date:** 2026-11-23
- **Sprint:** 62, slice 1

## Context

The test step runs the project's `test_command` and records its exit code,
duration, commit and output. It did not know how many tests ran. The pages
showed "Passed" alone, and the Checks tab showed the output's last line,
which for Python's unittest is a lone "OK" (owner, 2026-11-22).

Reading the count from the printed output would mean one parser for each
tool's wording, and it would be thrown away once Foreman reads each test's
result (owner direction 5, `docs/sprints/backlog.md`).

Two more facts shaped the decision:

- The step's records were all saved when the tests ended, so the step
  could not say when they started. The records also could not be followed
  while the tests ran.
- The Python on the owner's machine has expat 2.2.9, older than the release
  that limits entity expansion.

## Decision

1. **Foreman names a fresh empty directory in `FOREMAN_TEST_REPORT_DIR`**
   for each test run. The directory is outside the working copy and is
   removed after the run. A test command that writes JUnit XML reports
   there tells Foreman how many tests ran.
   - JUnit XML is the format pytest, vitest, jest, Playwright and
     unittest-xml-reporting already write. No tool is special.
   - A command that writes no report runs as before; the count is then
     unknown, not zero.
2. **Every `.xml` file in the directory is read, and the `<testcase>`
   elements are counted.** A case with `<failure>` or `<error>` failed, one
   with `<skipped>` was skipped, the rest passed. The totals on
   `<testsuite>` are not used, because tools fill them in differently.
3. **A report is refused, not parsed, when it:**
   - declares a document type or an entity (a JUnit report has neither);
   - is over 32 MB;
   - is a link.

   At most 200 files are read. Why a file was not read is recorded with the
   counts.
4. **`engine.test_run` carries `report`** (`tests`, `passed`, `failed`,
   `skipped`, `files`, or null) and **`report_problems`**. The checks
   (`facts.tests.counts`) and the task's runs (`runs[].tests`) serve the
   counts.
5. **A built-in step's records are saved as they happen,** as a human
   gate's already were. `engine.test_started` is saved when the tests
   start, and the output as it is printed.

## Consequences

- The pages say "Passed · 1,599 tests, 1 skipped" and "1,599 tests passed
  (1 skipped)". The Checks tab drops the output's last line when a report
  counted the tests.
- A project's test command has to write the report to be counted. For
  pytest that is `--junitxml="$FOREMAN_TEST_REPORT_DIR/pytest.xml"`; for
  vitest it is `--reporter=default --reporter=junit
  --outputFile.junit="$FOREMAN_TEST_REPORT_DIR/vitest.xml"`. Python's
  unittest writes none, so a unittest project needs unittest-xml-reporting
  (`python -m xmlrunner discover -s tests -o "$FOREMAN_TEST_REPORT_DIR"`).
- The same reports are where owner direction 5 starts: each test's name,
  result, time and failure message.
- A long test run writes one record per output line while it runs, instead
  of all of them at the end. The number of records does not change.
