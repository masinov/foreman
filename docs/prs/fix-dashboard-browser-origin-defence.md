# PR Summary: fix/dashboard-browser-origin-defence

## Summary

- Closes the two browser routes into a token-less loopback dashboard that
  the 2026-11-10 review reproduced: cross-site requests and DNS rebinding.
- Sprint 55 slice 1. Branched from `chore/phase0-baseline`; merge that first.

## Scope

- New `foreman/dashboard_guard.py`: Host, Origin and content-type decisions
  as pure functions.
- `foreman/dashboard_backend.py`: guard middleware on `/api` (intake
  exempt), JSON content type required for bodies, `?token=` on GET only,
  generated docs routes disabled, `trusted_hosts` parameter.
- `foreman/dashboard_runtime.py`: passes loopback host names when no token
  is configured, including through the reload environment.
- Not in scope: which settings may be changed over HTTP (slice 2), identity.

## Files changed

- `foreman/dashboard_guard.py` (new), `foreman/dashboard_backend.py`,
  `foreman/dashboard_runtime.py`
- `tests/test_dashboard_safety.py`
- `docs/adr/ADR-0016-dashboard-browser-origin-defence.md`,
  `docs/adr/README.md`, `docs/MANUAL.md`, `docs/STATUS.md`,
  `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- A reverse proxy that rewrites `Host` in front of a token-less dashboard
  now gets 403; configure a token or preserve the header.
- A non-browser client that sends a body without
  `Content-Type: application/json` now gets 400.
- A foreign-origin GET that used to return data without CORS headers now
  returns 403 (one existing test updated to assert that).

## Tests

- `python -m unittest discover -s tests`: 1001 pass, 1 skipped (12 new)
- `ruff check foreman tests scripts`: clean
- Live, against a scratch database on port 8379: cross-origin `text/plain`
  PATCH 403; `text/plain` PATCH without Origin 400; `Host:
  evil.example.com` 403; `/openapi.json` 404; the real page loads over
  `localhost` and `127.0.0.1`, lists tasks, and a same-origin settings
  PATCH returns 200.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A page on another origin cannot read or write through the API.
- A host name re-pointed at loopback is refused.
- The shipped frontend and the Vite dev flow work unchanged.

## Follow-ups

- Slice 2: host-level settings out of the general API; safe worktree prune.
- Typed API models, then re-enable the schema routes behind the token.
