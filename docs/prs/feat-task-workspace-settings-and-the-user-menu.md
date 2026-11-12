# PR Summary: feat/task-workspace-settings-and-the-user-menu

## Summary

- `/dashboard/settings` is built from `docs/design/dashboard-v7/15-workspace-settings.html`: Defaults for projects, Access, Notification channels, Runners and This machine, all from live data.
- A user menu sits at the far right of the top bar on every page: the identity the server reports, a link to workspace settings, and Sign out where it means something.
- New API reads and writes, each on the service the CLI already uses: `GET /session`, `GET /machine`, `GET /runners`, `GET /tokens`, `POST /projects/{id}/tokens`, `POST /tokens/{id}/revoke`, `GET /notification-channels`, `POST /projects/{id}/notification-channels`, `DELETE /notification-channels/{id}` (under `/api/v1`, and `/api`).

## Scope

- Defaults: workflows (with the projects that use each, from `/workspace`) and roles; each "Open" is a read-only dialog with the definition and the file it comes from. No create or edit buttons (out of scope).
- Access: tokens across projects (name, project, scopes, created, last used, revoked state). Create shows the secret once, in a dialog, with a Copy button; the secret exists only in that dialog's props and is dropped on close. Revoke is confirmed. Both reload the list. The identity-provider line says "none configured" and that people are identified by the token they use; the text comes from `identity_provider` in `/session` (always `null` today, there is no provider in Foreman).
- Channels: list, add (project, name, address, optional signing-key variable name) and remove (confirmed). Empty state says so.
- Runners: `foreman/runner/discovery.py` resolves each backend's executable on `PATH` (nothing is launched) and lists the models. Neither CLI can list the models it serves, so the column is headed "Models roles ask for": the `model` and `model_ladder` of the role definitions that use the backend, plus a note when a role names none and the runner's own default applies.
- This machine: database path (absolute), version, and the dashboard address the request came in on.
- Session: `none` authentication is "Local operator". With a dashboard token it is "Dashboard token" (the shared token has no name of its own; MANUAL says a shared token is not identity). Sign out is offered only for a token session: it forgets the stored token and reloads.
- Refactor: `foreman notify add` and the dashboard share `notifications.add_destination` (validation, duplicate-name check, id). No behaviour change for the CLI.
- Removed the old "Workspace settings" top-bar link on workspace pages; the user menu replaces it everywhere.

## Files changed

- Backend: `foreman/dashboard_access.py` (new), `foreman/dashboard/routers/access.py` (new), `foreman/runner/discovery.py` (new), `foreman/notifications.py` (`add_destination`), `foreman/cli/notify.py`, `foreman/dashboard/{app,context,schemas}.py`.
- Frontend: `frontend/src/pages/workspaceSettings/*` (page, five sections, dialogs), `frontend/src/app/UserMenu.jsx`, `Shell.jsx`, `App.jsx`, `pages.js`, `frontend/src/api/access.js`, `api/token.js`, styles (`workspaceSettings.css`, `shell.css`, `ui.css`, `tokens.css`), fixtures and tests.
- Tests: `tests/test_dashboard_access_api.py`, `frontend/src/pages/workspaceSettings/WorkspaceSettings.test.jsx`, `frontend/src/app/UserMenu.test.jsx`, `App.test.jsx` and `WorkspacePage.test.jsx` adjusted (the session read is now part of every page; the "not built" page test renders that page directly because every route now has a page).

## Migrations

- none

## Risks

- Signing out of a dashboard-token session leaves nothing to sign back in with: the rebuilt frontend has no screen that asks for a token (listed in `legacy-capabilities.md` as "no home yet"). Until that screen lands, a token user who signs out must set the token in browser storage by hand.
- The dashboard address is read from the request (`Host`), so behind a proxy it is the address the browser used, not the bind address.
- Tokens and channels belong to projects, so the workspace lists span projects and each create picks one. Names are unique per project only.
- The bundle (`foreman/dashboard_frontend_dist`) is rebuilt and checked locally but, as the repository rules say, not committed.

## Tests

- `./venv/bin/python -m unittest discover -s tests` (14 new API tests in `test_dashboard_access_api.py`: session, machine, runners, token create/list/revoke including that the secret is never listed and only its hash is stored, channel add/list/remove and validation, auth required on every new route).
- `npm --prefix frontend test` (300 tests; new: settings page sections, empty states, token create with one-time secret and copy, revoke confirmation, channel add/remove, runners and machine, user menu on every page, keyboard opening and Escape, sign out).
- `npm --prefix frontend run build`.
- `./venv/bin/python scripts/validate_repo_memory.py`.

## Screenshots or output examples

- `docs/prs/screenshots/feat-task-workspace-settings-and-the-user-menu/workspace-settings.png` (1440 wide, against a copy of the project database with one token and one channel added to the copy).
- Compared with the design: same section order, headings, notes, table structure, the identity-provider line and the narrow label column of This machine. Differences: rows are the shared table's height (the design draws tighter rows), tokens carry Scopes and Project columns and channels carry Project and Kind columns the design does not draw, and the drawing's "New workflow" and "New role" buttons are left out (out of scope).

## Acceptance criteria satisfied

- `/dashboard/settings` renders the five sections from live data, with empty states for tokens and channels.
- Token create shows the secret once, revoke is confirmed, both call the API and reload; endpoints have Python and frontend tests and go through `ForemanStore` token methods and `notifications.add_destination`.
- Runners and machine values come from the server (`/runners`, `/machine`), tested.
- The user menu is on every page, shows the server's identity, links to workspace settings, works from the keyboard; tested.
- Frontend and Python suites pass. The bundle is rebuilt but not committed (see Risks).

## Follow-ups

- A screen that asks for a dashboard token on 401 (so Sign out can be followed by signing in).
- Runner models: if either agent CLI gains a way to list its models, report those instead of the roles' choices.
- Named per-person identities (an identity provider); until then the session name is "Dashboard token" or "Local operator".
- Test a channel from the page (`foreman notify test`) and show its recent deliveries.
- Tighter table rows to match the drawing, which is a change to the shared Table and belongs to "Make the built pages match the design".
