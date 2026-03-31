# Sprint Archive: sprint-22-dashboard-backend-foundation

- Sprint: `sprint-22-dashboard-backend-foundation`
- Status: completed
- Goal: replace the raw stdlib dashboard server with an actual backend
  foundation before any dedicated frontend work continues
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/STATUS.md`
  - `docs/adr/ADR-0003-web-ui-api-boundary.md`
  - `docs/ARCHITECTURE.md`
  - `foreman/dashboard.py`
  - `foreman/dashboard_api.py`
  - `foreman/dashboard_backend.py`
  - `tests/test_dashboard.py`

## Final task statuses

1. `[done]` Replace the raw dashboard transport with a real web backend
   Deliverable: dashboard routes now run through FastAPI and uvicorn instead
   of `SimpleHTTPRequestHandler` and `ThreadingHTTPServer`.

2. `[done]` Preserve the current dashboard route surface on the new backend
   Deliverable: the legacy dashboard shell and the shipped JSON and streaming
   endpoints continue to work while the frontend remains transitional.

3. `[done]` Add backend-facing HTTP coverage
   Deliverable: dashboard regression tests now exercise real ASGI endpoints in
   addition to the extracted dashboard service layer.

## Deliverables

- `foreman/dashboard_backend.py` as the FastAPI transport layer
- `foreman/dashboard.py` reduced to the legacy shell plus uvicorn entrypoint
- `pyproject.toml` updated with FastAPI, uvicorn, and HTTP client
  dependencies
- dashboard tests upgraded to hit the ASGI app directly
- repo-memory rollover from backend foundation to React dashboard foundation

## Demo notes

- `./venv/bin/python -m unittest tests.test_dashboard -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-23-react-dashboard-foundation`: replace the legacy shell with the
  dedicated React frontend
- `sprint-24-product-surface-hardening`: remove or finish remaining stub and
  structurally weak product surfaces
