# PR Summary: fix/test-reports-read-in-full

## Summary

- **The fault:** FOR-50's test step counted 1,242 tests. Foreman's suite has
  more than 1,600 Python tests and 493 frontend tests.
  - The reader stopped at 200 report files, and Foreman's Python tests write
    one per test class, 272 in all.
  - Files are read in name order and "TEST-…" sorts before `frontend.xml`, so
    the frontend's report was never read.
  - The run recorded "272 reports; Foreman read the first 200.", but the page
    showed the short count.
- **The change** (owner, 2026-11-24): "Shouldn't all content be read?", then
  "Go ahead" on fixing the reader rather than each project's test command.
  - Every report is read in full, with no limit on how many files or how
    large.
  - Each file is read a piece at a time with expat, keeping only the running
    totals, so its size costs time, not memory. The limits were there only
    because each file was loaded whole.
  - The refusals that are about trickery stay. Reading stops where a document
    type declaration starts, before any entity is defined or used. Links are
    not followed.
  - A report that breaks half-way adds nothing to the counts and is named as
    not read.
- No project's test command changes.

## Scope

- `foreman/engine/builtins/test_report.py`: `_count` reads with expat in
  64 KB pieces; `MAX_REPORT_BYTES` and `MAX_REPORT_FILES` are removed. Failed
  tests are still named up to 50, and the count stays whole across files.

## Files changed

- `foreman/engine/builtins/test_report.py`
- `tests/test_test_report.py`:
  - 300 files plus a report of 100,000 cases, all read;
  - a report cut half-way;
  - only a case's own elements decide how it ended;
  - failures past the named ones still count across files.
- `docs/adr/ADR-0035-tests-are-counted-from-junit-reports.md` (amended),
  `CHANGELOG.md`, `docs/STATUS.md`.

## Migrations

None.

## Risks

- A test command that writes a very large amount of XML now makes the test
  step take longer to finish reading it. It no longer makes it use more
  memory.

## Tests

- `tests.test_test_report` and `tests.test_builtins`, ruff and
  `lint-imports`.
- The whole Python suite before the merge.
- A real run: unittest-xml-reporting and vitest wrote their reports into one
  folder (11 Python tests, 50 frontend tests), and the reader counted 61 from
  2 files with no problems.

## Acceptance criteria

- Every report a test command writes is counted, whatever the number of
  files or their size.

## Follow-ups

- None. The next test step that runs Foreman's own suite will show its full
  count.
