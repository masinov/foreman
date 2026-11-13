# fix/ci-unused-import

## Summary

CI's Python job failed at `ruff check` on every push from `5d42fc9`
(2026-11-13) onward: `foreman/dashboard_service.py` imported `Run` and no
longer used it. The frontend job passed throughout, and the Python tests were
run locally before each merge, but `ruff` was not installed in the local
virtual environment, so the failure went unseen for thirteen merges.

## Scope

The import is removed. `ruff` is installed in the local environment (it is a
declared development dependency).

## Tests

`./venv/bin/ruff check foreman tests scripts` (clean),
`./venv/bin/python -m unittest discover -s tests`.

## Follow-ups

Read CI after each push, not only run the suites locally.
