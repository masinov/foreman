# refactor/dashboard-api

## Summary

Sprint 57 slice 6a. The dashboard API is routed by resource, versioned, and
has one error shape. ADR-0019.

## Scope

- `foreman/dashboard/app.py`: the application factory (was
  `foreman/dashboard_backend.py`, which is now a re-export).
- `foreman/dashboard/context.py`: `ApiContext` (`with_api`,
  `require_manager`), request helpers, `API_PREFIXES`.
- `foreman/dashboard/routers/`: nine modules, 40 routes, bodies unchanged.
- Each router is mounted under `/api/v1` and `/api`.
- `_error_body(message, code)` everywhere an error is returned, plus
  handlers for framework HTTP errors, request validation and unhandled
  exceptions.
- `_is_intake_path` recognises both prefixes.
- Frontend: `API_BASE = "/api/v1"` in `api.js`.

## Files changed

`foreman/dashboard/` (new package), `foreman/dashboard_backend.py` (shim),
`frontend/src/api.js` and its test, rebuilt bundle,
`tests/test_dashboard_api.py` (new), ADR-0019, changelog, sprint.

## Migrations

None.

## Risks

- A client that parsed FastAPI's `{"detail": ...}` on a 404 or 422 inside
  `/api` now gets the envelope, and a bad query parameter is 400, not 422.
- The intake path check is security-relevant (it decides where a project
  token is valid); it is covered for both prefixes and for look-alikes.

## Tests

Full Python suite, `ruff check`, frontend `vitest` and build.

## Acceptance criteria satisfied

Slice 6a as written in `docs/sprints/current.md`.

## Follow-ups

Slice 6b.
