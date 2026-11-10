# ADR-0016: Dashboard Browser-Origin Defence

- Status: accepted
- Date: 2026-11-10
- Deciders: engine team

## Context

The dashboard binds to loopback with no token by default. That keeps other
machines out, but the operator's browser can reach it, and so can any web
page that browser loads. The 2026-11-10 review reproduced both routes in:

- a cross-site `fetch` with `Content-Type: text/plain` is sent without a
  preflight, and the API parsed the body as JSON regardless of its declared
  type, so a hostile page could create projects and change settings;
- the API answered any `Host` header, so a hostile name re-pointed at
  127.0.0.1 (DNS rebinding) made the page same-origin with the dashboard.

Project settings include shell commands the engine runs, so either route
ended in code execution on the operator's machine.

## Decision

Every `/api` request except intake passes a guard
(`foreman/dashboard_guard.py`) before any credential check:

1. **Host.** When the API has no token, the runtime passes the host names
   the dashboard answers to (`localhost`, `127.0.0.1`, `::1`, and the bind
   host). Any other `Host` header is refused with 403. With a token the
   check is off: a rebound page does not hold the token.
2. **Origin.** A request carrying `Origin` must match the request's own
   `Host`, an `--allowed-origin` entry, or the Vite dev server in dev mode.
   A state-changing request the browser labels `Sec-Fetch-Site: cross-site`
   is refused even without `Origin`.
3. **Content type.** A non-empty request body must be declared
   `application/json`, which a browser cannot send cross-origin without a
   preflight the API never approves.

Also: the `?token=` query form is honoured on GET only (the event stream
needs it; nothing else should put a credential in a URL), and the generated
`/docs`, `/redoc` and `/openapi.json` routes are disabled until the API has
typed models and those routes sit behind the token.

Intake is exempt from the guard. It is a server-to-server route that
authenticates its own project API token, which no web page holds.

## Alternatives rejected

- **Always require a token, generated at startup and injected into the
  served page.** It adds a bootstrap path and storage for a secret, and the
  Host and Origin checks already close the browser routes. A token remains
  required for non-loopback binds.
- **Starlette's `TrustedHostMiddleware`.** It applies to every route and
  every mode; the check here must be off when a token is configured, must
  skip intake, and must answer in the API's error envelope.

## Consequences

- A reverse proxy in front of a token-less loopback dashboard must preserve
  the `Host` header or the operator must configure a token.
- Non-browser clients are unaffected unless they send a foreign `Origin` or
  a body without a JSON content type.
- Other local processes can still call a token-less dashboard. That is the
  loopback trust model and is unchanged.
- This closes the browser route only. Which settings may be changed over
  HTTP at all is sprint 55 slice 2.
