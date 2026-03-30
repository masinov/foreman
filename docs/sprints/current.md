# Current Sprint

- Sprint: `sprint-19-watch-live-tail-alignment`
- Status: active
- Goal: align `foreman watch` with the dashboard live transport and the
  spec's live-tail intent
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/STATUS.md`
  - `foreman/cli.py`
  - `foreman/dashboard.py`
  - `tests/test_cli.py`
  - `tests/test_dashboard.py`

## Included tasks

1. `[todo]` Define the live-tail boundary for `foreman watch`
   Deliverable: the CLI watch command follows an explicit streaming model that
   matches the product's live-activity intent without inheriting dashboard-only
   UI assumptions.

2. `[todo]` Replace bounded polling snapshots with incremental updates
   Deliverable: `foreman watch` can stream ongoing persisted activity instead
   of requiring fixed `--iterations` polling loops.

3. `[todo]` Document watch and dashboard alignment
   Deliverable: repo docs explain how the CLI tail relates to the dashboard's
   live stream, including any remaining scope or UX differences.

## Excluded from this sprint

- migration framework work
- backend auth and service-reachability health checks
- multi-user dashboard concerns
- a separate pub-sub or websocket transport layer

## Acceptance criteria

- `foreman watch` no longer depends on bounded polling snapshots for its core
  live-tail path
- automated tests cover the aligned watch behavior at the CLI and dashboard
  boundary where practical
- docs explain the live-tail boundary clearly enough for operators and fresh
  agents
