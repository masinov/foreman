# PR Summary: chore/tests-in-parallel

## Summary

- **The Python suite runs in parallel** (owner, 2026-11-24: "The parallel
  Python tests could be a nice simple addition... Perhaps there is already
  a framework we can just hook into").
  - The framework is pytest with pytest-xdist. `pytest -n auto` starts one
    worker per processor core, which is the "detect the resources" the
    owner asked about.
  - The tests are unittest `TestCase`s, and pytest runs them unchanged.
- **Measured on this machine** (16 cores, 125 GB): the whole suite takes
  52–54 s in parallel, against about 5 minutes on one worker.
  - Three parallel runs in a row: 1,680 passed and 7 skipped each time, with
    no test changed. No test shares state that collides.
  - The 7 skipped are the old dashboard's browser tests in
    `tests/test_e2e.py`. pytest collects them as 7 tests where unittest
    counted the skipped module as 1, so the total is 1,687, not 1,681.
- **The report:** pytest writes the JUnit XML the test step counts
  (ADR-0035) itself, with `--junitxml`, in one file. Foreman's reader counted
  1,687 tests (1,680 passed, 7 skipped) from it. unittest-xml-reporting leaves
  the dev dependencies.
- **Dependencies:** pydantic and starlette, which Foreman's code imports
  directly, are declared as runtime dependencies. They came only through
  FastAPI before. Foreman keeps every dependency in `pyproject.toml` (runtime
  and the `dev` extra), which CI and every task's working copy install from.
  It has no `requirements.txt`.

## Scope

- `pyproject.toml`: the `dev` extra gains pytest and pytest-xdist, loses
  unittest-xml-reporting, and gains `[tool.pytest.ini_options]`; pydantic and
  starlette are declared.
- `.github/workflows/ci.yml`: `pytest tests -n auto -q`.
- The commands in `AGENTS.md`, `README.md`, `docs/TESTING.md`,
  `docs/MANUAL.md` and `docs/STATUS.md`.
- After merging, Foreman's own `test_command` (a project setting) runs
  `./venv/bin/python -m pytest tests -n auto -q --junitxml="$FOREMAN_TEST_REPORT_DIR/python.xml"`
  in place of the xmlrunner command.

## Files changed

- The files above, `CHANGELOG.md` and this note.

## Migrations

None in the database. The setting change is made with `foreman config`.

## Risks

- **Test step CPU:** the test step now uses every core for about a minute.
  On a machine shared with other work that is the intent of `-n auto`. A
  smaller number can be set in the command.
- **Assay is unchanged:** it keeps its own `requirements.txt` and xmlrunner
  command.

## Tests

- Three full parallel runs.
- The JUnit report read by `read_reports`.
- `pip check`.
- ruff and the repo-memory check.

## Acceptance criteria

- The suite passes in parallel, repeatedly.
- The test step's count is complete.
- CI runs it the same way.

## Follow-ups

- Test tiers, for the owner to decide (direction 5).
