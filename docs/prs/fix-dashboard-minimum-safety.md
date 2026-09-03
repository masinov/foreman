# PR Summary: fix/dashboard-minimum-safety

## Summary

Sprint 53, slice 5. The minimum safety a shared dashboard needs before
Phase 1 adds real identity: no wildcard CORS, a shared access token on
every `/api` route, a refusal to bind off-loopback without that token, the
full-access manager chat kept loopback-only unless explicitly allowed,
project repository paths validated, and the events page size bounded. The
frontend learns to carry the token and to ask for it.

## Scope

- **Backend** (`foreman/dashboard_backend.py`): `create_dashboard_app`
  gains `auth_token`, `allowed_origins`, and `manager_enabled`. A middleware
  rejects `/api` requests without the token (`Authorization: Bearer`,
  `X-Foreman-Token`, or `?token=` for the event stream) with 401 and
  `WWW-Authenticate: Bearer`; comparison is constant-time. CORS middleware
  is added only for an explicit origin allowlist with explicit methods and
  headers. The manager routes (`meta/message`, `meta/supervise`,
  `DELETE meta/session`) raise 403 when the manager is disabled; history
  stays readable. `GET /api/sprints/{id}/events` rejects `limit < 1` and
  caps it at 500. `create_dashboard_app_from_env` reads
  `FOREMAN_DASHBOARD_TOKEN`, `FOREMAN_DASHBOARD_ALLOWED_ORIGINS`, and
  `FOREMAN_DASHBOARD_MANAGER` for reload mode.
- **Runtime** (`foreman/dashboard_runtime.py`): `is_loopback_host` and
  `dashboard_security_policy` decide the posture. A non-loopback bind
  without a token raises unless `allow_insecure_network`; the manager is
  enabled only on loopback or with `allow_remote_manager`; notices are
  printed at startup. `run_dashboard_server` threads the policy into the app
  and the reload environment.
- **CLI** (`foreman dashboard`): `--token` (default
  `FOREMAN_DASHBOARD_TOKEN`), `--token-file`, `--allowed-origin`
  (repeatable), `--allow-insecure-network`, `--allow-remote-manager`.
- **Service** (`foreman/dashboard_service.py`): `create_project` rejects a
  `repo_path` that is not an existing directory containing `.git`, and,
  when `FOREMAN_DASHBOARD_REPO_ROOTS` is set, one outside those roots.
- **Frontend** (`frontend/src/api.js`, `App.jsx`, `styles.css`): the request
  layer sends the stored token as a bearer header, puts it on the event
  stream URL, and raises `UnauthorizedError` on 401; the app then renders
  a token prompt that stores the token in `localStorage` and reloads.
  Bundle rebuilt.

## Files changed

- `foreman/dashboard_backend.py`, `foreman/dashboard_runtime.py`,
  `foreman/dashboard_service.py`, `foreman/cli.py`
- `frontend/src/api.js`, `frontend/src/App.jsx`, `frontend/src/styles.css`,
  `frontend/src/api.test.js` (new), `foreman/dashboard_frontend_dist/`
- `tests/test_dashboard_safety.py` (new, 12 tests), `tests/test_dashboard.py`
- `docs/sprints/current.md`, `docs/STATUS.md`, `docs/MANUAL.md`,
  `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `README.md`, `CHANGELOG.md`

## Migrations

- None.

## Risks

- **Behavior change:** cross-origin browser calls no longer work unless an
  origin is allowlisted. The shipped frontend is same-origin (served by
  FastAPI, or proxied by Vite), so normal use is unaffected.
- **Behavior change:** `foreman dashboard --host 0.0.0.0` now fails without a
  token or `--allow-insecure-network`.
- **Behavior change:** creating a project through the API requires a real
  git repository path. The CLI `foreman init` path is unchanged.
- A shared token is not identity; every holder is the same actor. Phase 1
  adds login and actor columns. The token is stored in the browser's
  `localStorage`, which is appropriate for a single-team internal tool but
  not for a public deployment.
- The manager chat remains a full-access agent session where it is
  enabled; this slice only keeps it off the network by default.

## Tests

- `./venv/bin/python -m unittest discover -s tests` — 661 passing (was 649;
  +12 in `tests/test_dashboard_safety.py`).
- `npm --prefix frontend test` — 18 passing (+5 in `api.test.js`);
  `npm --prefix frontend run build` clean.
- `scripts/validate_repo_memory.py` clean; `git diff --check` clean.

## Acceptance criteria satisfied

- `/api` routes return 401 without the configured token and accept it via
  header or query; the shell and assets load without it,
- no `Access-Control-Allow-Origin` header unless the origin is allowlisted,
- manager routes return 403 when the manager is disabled,
- a non-loopback bind without a token is refused; explicit opt-ins work,
- project creation rejects missing, non-git, and out-of-root paths,
- the frontend sends the token and prompts for it on 401.

## Follow-ups

- Sprint 53 slice 6 (cleanup).
- Phase 1: login and per-user identity replacing the shared token; the
  manager chat launched through the runner with a declared tool set.
