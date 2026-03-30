# Sprint Archive: sprint-14-dashboard-streaming-transport

- Sprint: `sprint-14-dashboard-streaming-transport`
- Status: completed
- Goal: replace polling-only dashboard refresh with an explicit live event
  transport that keeps activity and task state current
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/adr/ADR-0002-dashboard-data-access-boundary.md`
  - `foreman/dashboard.py`
  - `foreman/store.py`
  - `foreman/cli.py`

## Final task statuses

1. `[done]` Add a live dashboard event transport endpoint
   Deliverable: the dashboard now exposes a dedicated sprint event stream for
   incremental persisted event delivery instead of periodic full refresh
   polling.

2. `[done]` Wire the dashboard activity feed to the live transport
   Deliverable: new activity appears in the UI through an `EventSource`
   subscription without polling the full event list every cycle.

3. `[done]` Keep task state and transport semantics aligned
   Deliverable: incoming streamed events trigger debounced sprint and task
   refresh so board state and selected task detail stay current while the page
   is open.

## Deliverables

- sprint-scoped store queries for recent and incremental event delivery
- threaded dashboard HTTP serving so long-lived stream connections do not
  block action endpoints
- a dedicated `/api/sprints/<id>/stream` dashboard transport endpoint backed
  by server-sent events
- dashboard client subscription and refresh wiring for live activity updates
- regression coverage for sprint-scoped event ordering and dashboard stream
  wiring
- repo-memory rollover from dashboard streaming transport to engine DB
  discovery

## Demo notes

- `./venv/bin/python -m unittest tests.test_store tests.test_dashboard -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-15-engine-db-discovery`: remove the bootstrap requirement for
  explicit `--db` paths in normal SQLite-backed CLI flows
- `sprint-16-security-review-workflow`: add a declarative security review
  workflow variant with orchestrator and CLI coverage
- `sprint-17-native-backend-preflight-checks`: add explicit backend
  availability checks before native execution
