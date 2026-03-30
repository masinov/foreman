# Current Sprint

- Sprint: `sprint-14-dashboard-streaming-transport`
- Status: active
- Goal: replace polling-only dashboard activity refresh with an explicit live
  transport that keeps activity and task state current
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/adr/ADR-0002-dashboard-data-access-boundary.md`
  - `foreman/dashboard.py`
  - `foreman/store.py`
  - `foreman/cli.py`

## Included tasks

1. `[todo]` Add a live dashboard event transport endpoint
   Deliverable: the dashboard has a dedicated endpoint for incremental event
   delivery instead of relying on periodic full refresh polling.

2. `[todo]` Wire the dashboard activity feed to the live transport
   Deliverable: new activity appears in the UI without manual refresh and
   without polling the full event list every cycle.

3. `[todo]` Keep task state and transport semantics aligned
   Deliverable: task cards and selected task detail stay in sync with incoming
   events, and the repo docs explain how this transport relates to the current
   bounded `foreman watch` behavior.

## Excluded from this sprint

- authentication and multi-user concerns
- security review workflow variant
- event-retention pruning
- engine-level database discovery

## Acceptance criteria

- the dashboard receives new persisted events without full-list polling
- activity and task state stay current while the page is open
- the transport boundary is documented clearly enough for the next slice to
  build on it without reverse-engineering the dashboard code
