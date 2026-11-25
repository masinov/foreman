# PR Summary: fix/tests-browser-plugin-off-by-default

## Summary

FOR-65 (the trial of the new reviewer) blocked on 2026-11-25 without
reaching review: Develop and Test alternated until the step limit. The
cause was not the task. Since 2026-11-25 the worktree setup installs the
`e2e` extra, so the reviewer can take screenshots. That brings in
pytest-playwright, and in Foreman's test step:
- `tests/test_e2e.py` was no longer skipped (it checked only that the
  playwright package imports) and failed to launch Chromium, which is not
  installed and not supported on this Ubuntu 20.04: 7 errors a run;
- the plugin's session browser fixture left an event loop running on its
  xdist worker, so later `asyncio.run()` calls on that worker failed: 2 to 8
  other tests a run, a different set each time.

The developer said so each round and changed nothing, rightly.

- `pyproject.toml`: `addopts = "-p no:playwright"`. The plugin is off in an
  ordinary run, whatever is installed.
- `tests/test_e2e.py`: also skips when the plugin is off, through a string
  `skipif` condition evaluated with the run's config before any fixture
  (the plugin's `page` fixture does not exist then).
- `docs/TESTING.md`: how browser tests run (`-o addopts=""`), and that the
  review screenshots do not need the plugin.

## Scope

Test configuration and one test module's skip rule.

## Files changed

- `pyproject.toml`
- `tests/test_e2e.py`
- `docs/TESTING.md`
- this note.

## Migrations

None.

## Risks

- Browser tests now need an explicit opt-in. They were skipped everywhere
  before (no Playwright in the operator venv or CI), so nothing that ran
  stops running.

## Tests

- With FOR-65's worktree venv (the `e2e` extra installed): whole suite,
  twice: `1769 passed, 11 skipped`, exit 0. Before: 7 to 15 failures a run.
- With the operator venv (no plugin): `1769 passed, 11 skipped`, exit 0.
- `pytest -o addopts="" tests/test_e2e.py`: the plugin loads and the
  module reaches its own checks.

## Acceptance criteria satisfied

- The whole suite passes in a venv with the `e2e` extra.

## Follow-ups

- `tests/test_e2e.py` tests the old dashboard (backlog, "No browser tests
  for the current dashboard").
