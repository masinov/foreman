# PR Summary: fix/tests-cli-install-once

## Summary

- **The fault:** the first run of Foreman's real test command in parallel
  (`pytest -n auto`) had 13 errors, all in `tests/test_cli.py`.
  - `ForemanCLISmokeTests.setUpClass` reinstalled Foreman into the shared
    virtualenv (`pip install -e .`) whenever the virtualenv already pointed
    at this checkout, which is the normal case.
  - With several workers, each ran its own `setUpClass` at once, and one
    found `venv/bin/foreman` missing while another was rewriting it.
  - Three earlier parallel runs had passed by timing alone.
- **The change:**
  - The reinstall is skipped when the editable install already points at
    this checkout and the console script exists. An editable install has
    nothing to update.
  - When it is not installed yet, the install runs under an exclusive file
    lock in the virtualenv (`.foreman-test-install.lock`): one worker
    installs, and the others wait and find it done.

## Scope

- `tests/test_cli.py`

## Files changed

- `tests/test_cli.py` and this note.

## Migrations

None.

## Risks

None found.

## Tests

- Foreman's exact `test_command`, with `FOREMAN_TEST_REPORT_DIR` set, three
  times in a row:
  - frontend build;
  - `pytest -n auto` (1,680 passed, 7 skipped);
  - the frontend suite.

  It took 63–64 s each time. `read_reports` counted 2,220 tests from the two
  files.

## Acceptance criteria

- The suite passes in parallel, whatever the timing.

## Follow-ups

None.
