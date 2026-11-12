# chore/frontend-bundle-out-of-git

## Summary

Owner decision, 2026-11-12 (the item left open as sprint 57 slice 9). The
built dashboard bundle is no longer committed.

## Why now

Sprint 58 runs frontend tasks through Foreman one after another. Each one
rebuilt `foreman/dashboard_frontend_dist` under new hashed file names, so any
two frontend branches open at the same time conflicted there. Five merges
were sent back to their developer for that alone, one task four times.

## Scope

- `foreman/dashboard_frontend_dist/` is removed from git and ignored;
  `.gitattributes` (which only described it) is gone.
- `foreman/dashboard_runtime.py`: `prepare_dashboard_assets()` builds the
  bundle with npm when it is missing or older than the frontend source, in a
  source checkout; `FOREMAN_DASHBOARD_NO_BUILD=1` turns that off. An
  installed package has no source and must contain the bundle.
- `foreman/dashboard/app.py`: the app starts without a bundle; `/dashboard`
  answers 503 with how to build it; the index is read per request, so a
  rebuilt bundle is served without a restart.
- CI: the Python job builds the frontend before the tests; the frontend job
  no longer compares a committed bundle.
- ADR-0020 decision 10 amended; `docs/TESTING.md`, `docs/RELEASES.md`,
  `README.md`, `docs/ARCHITECTURE.md`; the open decision leaves the backlog.

## Files changed

Runtime, app, CI, `.gitignore`, tests (`tests/test_dashboard_bundle.py` new,
`tests/test_dashboard.py`), docs.

## Migrations

None. The project's `test_command` setting changes to build before the
Python suite (operator action, recorded in the sprint doc).

## Risks

- A checkout needs Node to serve the dashboard. A package built by the
  release steps does not.
- Open frontend branches still carry bundle changes; each conflicts once
  more when it merges, and is resolved by deleting the bundle from the
  branch.

## Tests

`tests/test_dashboard_bundle.py` (staleness, build steps, missing npm, failed
build, the opt-out, the API without a bundle); whole suite; ruff.

## Follow-ups

A build hook so `python -m build` builds the frontend itself.
