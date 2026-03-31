# ADR-0004: Dashboard Backend Framework

## Status

Accepted

## Context

Foreman's dashboard no longer needs only a service boundary. It also needs a
real web backend.

After `sprint-21-dashboard-api-extraction`, the repo had:

- an extracted dashboard service layer in `foreman/dashboard_service.py`,
- a runtime wrapper still coupled to the legacy dashboard shell behavior,
- raw HTTP delivery built on `SimpleHTTPRequestHandler` and
  `ThreadingHTTPServer`.

That transport shape is not acceptable for the product:

1. it is too primitive for a durable web backend,
2. it makes backend testing weaker than it should be,
3. it leaves the upcoming React frontend without a proper server foundation,
4. it keeps product delivery too close to a bootstrap prototype shape.

ADR-0003 already established that the product direction is a dedicated React
frontend plus a Python backend API. The remaining unresolved question was what
kind of Python backend should become the product baseline.

## Decision

Foreman's dashboard backend will use **FastAPI** as its HTTP framework and
**uvicorn** as its runtime server.

The active backend split is:

- `foreman/dashboard_service.py` owns store-backed dashboard reads, actions, and
  stream payload shaping,
- `foreman/dashboard_backend.py` owns FastAPI routing, request parsing,
  response delivery, and SSE transport,
- `foreman/dashboard_runtime.py` owns the CLI runtime entrypoint, built-asset
  guard, and frontend-dev launch behavior for `foreman dashboard`.

New dashboard backend work should target the FastAPI application, not new
stdlib handlers or ad hoc HTTP transport code.

## Consequences

### Positive

- establishes a real backend foundation before the React rewrite
- gives the dashboard a durable ASGI transport and clearer routing structure
- makes backend HTTP behavior testable through the app itself
- provides a more realistic product seam for future auth, deployment, and API
  evolution

### Negative

- adds new runtime dependencies to the Python package
- leaves a temporary period where backend runtime and frontend workflow still
  need explicit development ergonomics after the transport migration
- does not by itself solve frontend architecture or browser-level validation

## Follow-through requirements

- keep dashboard HTTP behavior on FastAPI while React work proceeds
- avoid adding new product routes through raw stdlib server patterns
- add backend-facing HTTP tests when dashboard transport behavior changes
- keep the runtime wrapper thin and avoid moving dashboard product behavior
  back into it now that React owns rendering

## References

- `docs/adr/ADR-0003-web-ui-api-boundary.md`
- `foreman/dashboard_runtime.py`
- `foreman/dashboard_service.py`
- `foreman/dashboard_backend.py`
- `docs/ARCHITECTURE.md`
- `docs/STATUS.md`
