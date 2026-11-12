# PR Summary: chore/task-remove-the-old-frontend-now-and-keep-a-checklist-of-what-it-could-do

## Summary

- Removes the pre-v7 frontend and `/dashboard/legacy` now, by owner decision of 2026-11-12, instead of in the sprint's last slice.
- Before deleting, records everything the old application could do or see in `docs/design/dashboard-v7/legacy-capabilities.md`, by screen, with the endpoint, the ADR-0020 route and a status (built, slice N, or no home yet). Ten capabilities have no home yet and are listed at the end of that file.
- The shared "being rebuilt" page is now "This page is not built yet". It links nowhere and names the terminal commands from `docs/MANUAL.md` that do the same job (for example `foreman approve <task-id>`, `foreman board`, `foreman config <project-id>`).

## Scope

- Deleted `frontend/src/legacy/` (app, components, styles, api client, formats, routing, and their tests).
- `app/main.jsx` mounts the one application; `paths.js` loses the legacy constants and helpers; `isAppPath` is every path under `/dashboard`. `/dashboard/legacy` therefore matches no route and renders the not-found page.
- `routes.js`: `legacyHref` and `legacyExact` replaced by an optional `cli(params)` per route.
- No server code existed only for the legacy address (the server already serves the one shell for every `/dashboard/*` path), so none was removed. No API endpoint was removed and the `/api` alias stays (ADR-0019).
- ADR-0020 decision 11 amended in place; `docs/STATUS.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md` updated.
- Not touched, per sprint rules: `CHANGELOG.md`, `docs/sprints/current.md`.

## Files changed

- `docs/design/dashboard-v7/legacy-capabilities.md` (new)
- `frontend/src/legacy/**` (deleted)
- `frontend/src/app/{main.jsx,paths.js,router.jsx,routes.js,App.test.jsx,routes.test.js}`
- `frontend/src/pages/status/RebuildingPage.jsx`, `frontend/src/styles/status.css`
- `foreman/dashboard_frontend_dist/**` (rebuilt: one entry chunk, no `mountLegacy` or `client` chunks)
- `tests/test_dashboard.py`, `tests/test_e2e.py`
- `docs/adr/ADR-0020-dashboard-design-v7-and-frontend-structure.md`, `docs/STATUS.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`

## Migrations

- none

## Risks

- Until the slices in the checklist land, some things can only be done from a terminal or the API: sprint reorder, activate, complete, cancel and delete; registering a project; pending sprint-order decisions (task-b1e9a964d00e); manager chat; settings; task actions other than approving a merge from Needs you. The checklist names each.
- `tests/test_e2e.py` was rewritten for the rebuilt workspace, project page, not-built page and the not-found legacy address. Playwright and pytest are not installed here, so it was compiled but not run (it skips without Playwright, as before).
- The access-token prompt is gone with no replacement; a dashboard bound with a token will show API errors rather than ask for one (item 1 in the checklist).

## Tests

- `npm --prefix frontend test`: 22 files, 131 tests pass (new: not-built page names commands and has no link, no "legacy" text; `/dashboard/legacy` renders not-found; `cli` commands per route).
- `npm --prefix frontend run build`: bundle rebuilt and committed.
- `./venv/bin/python -m unittest discover -s tests`: 1233 tests, OK (1 skipped). Only `test_fastapi_dashboard_assets_route_returns_built_bundle` changed (it expected a `mountLegacy` chunk); no API test was modified.
- `./venv/bin/python scripts/validate_repo_memory.py`.

## Screenshots or output examples

- n/a (jsdom only; no real browser on the host)

## Acceptance criteria satisfied

- `legacy-capabilities.md` exists with endpoint, route and status per capability, and names every capability with no home yet.
- Nothing under `frontend/src/legacy` remains or is imported; `/dashboard/legacy` renders not-found (tested in `App.test.jsx` and `routes.test.js`).
- The not-built page has no link and names a command where one exists (tested).
- No API endpoint removed.
- ADR-0020 decision 11 amended; `docs/STATUS.md` consistent.
- Frontend tests pass, bundle committed, Python suite passes.
- No dependency added.

## Follow-ups

- Decide each of the ten "no home yet" items in `legacy-capabilities.md`: give it a slice, or record that it is dropped. Notably registering a project, sprint order/activate/complete/cancel/delete, and the access-token prompt.
- Slice 13 ("Remove the old frontend and /dashboard/legacy") is now mostly done by this task; what remains of it is the ESLint step and checking `docs/ARCHITECTURE.md` and `docs/TESTING.md`.
- `docs/sprints/current.md` and `CHANGELOG.md` need their entries when this lands (slice 1's "old application moved to /dashboard/legacy" and the constraint that it stays are now out of date).
