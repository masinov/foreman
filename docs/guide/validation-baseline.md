# Validation baseline

What is run before work is called done, and what CI runs. Test counts are
those of 2026-11-26 and drift; the commands do not. Moved from
`docs/STATUS.md` on 2026-11-26. `docs/TESTING.md` says how to write tests.

- `./venv/bin/python -m pytest tests -n auto -q` (1687 tests: the 1681
  unittest runs and the 6 browser tests of `test_e2e.py`, skipped without
  Playwright; about a minute)
- `npm --prefix frontend run lint`, `npm --prefix frontend test` (533 tests) and `npm --prefix frontend run build`
- `ruff check foreman tests scripts` (pyflakes and syntax rules)
- `lint-imports`: the layers contract in `.importlinter` (ADR-0032; needs
  Python 3.11, so CI runs it on the 3.12 job)
- `./venv/bin/python scripts/validate_repo_memory.py`
- CI runs all of the above; its Python job builds the frontend first, since
  the bundle is not in git (`.github/workflows/ci.yml`).
- The look: `scripts/dashboard_shot.mjs` against the rules in
  `docs/TESTING.md` ("Checking the look").
