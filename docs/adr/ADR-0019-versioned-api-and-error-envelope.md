# ADR-0019: The Dashboard API Is Versioned And Has One Error Shape

- Status: accepted
- Date: 2026-11-11
- Deciders: engine team

## Context

The dashboard API grew as 40 route functions nested inside one application
factory, all under `/api`. Other systems already call it (the intake
endpoint, ADR-0013), and the frontend is about to be rebuilt against it.
Three things made it hard to depend on:

- There was no version in the path, so no route could change shape without
  breaking whoever called it.
- Errors had two shapes. Foreman's own were `{"error": "..."}`; an unknown
  route, a wrong method or a bad query parameter came back in FastAPI's
  `{"detail": ...}`, and an unhandled exception as a bare 500.
- The routes could not be read or tested by resource.

## Decision

1. The API is served under `/api/v1`. The same routes also answer under
   `/api`, the original path, as an alias. New clients use `/api/v1`; the
   shipped frontend does. The alias is removed only in a release that says
   so.
2. Every error body, from a route, the authentication middleware, the
   browser-origin guard, the framework or a bug, is
   `{"error": "<a sentence>", "code": "<kind>"}`. The codes are
   `not_found`, `invalid_request`, `unauthorized`, `forbidden`,
   `not_permitted`, `method_not_allowed`, `action_failed`, `http_error` and
   `internal_error`. `error` stays a string, so a client that read only it
   keeps working.
3. An unhandled exception answers `internal_error` with no detail of what
   went wrong; the traceback goes to the `foreman.dashboard` log.
4. Routes live in `foreman/dashboard/routers/`, one module per resource,
   each exposing `build_router(ctx)`. They carry no prefix; the application
   mounts each under every prefix in `API_PREFIXES`.
5. Path-based rules (which credential is valid where) recognise every
   prefix. The project API token is valid on
   `<prefix>/projects/{id}/intake` and nowhere else, under both.

## Consequences

- A breaking change to a route goes to `/api/v2`; `/api/v1` keeps its shape.
- Request and response bodies are still untyped dicts. Typed models,
  pagination on list routes, handlers off the event loop and a project-level
  event stream are the next slice and can land inside v1 where they do not
  change a shape.
- `foreman.dashboard_backend` remains as a module that re-exports the
  application factory, because the reload target and existing imports name
  it.
