# ADR-0002: Dashboard Data-Access Boundary

## Status

Accepted

## Context

The Foreman dashboard needs to display project overview, sprint boards, and activity feeds from persisted SQLite state. We need to define how the HTTP API layer accesses this data.

Options considered:

1. **Direct store access**: Dashboard handler calls `ForemanStore` methods directly
2. **Separate read models**: Dashboard defines its own query layer over SQLite
3. **Projections**: Dashboard consumes pre-computed projections updated by the orchestrator

## Decision

The dashboard uses **direct store access** through `ForemanStore` read methods.

The current dashboard service layer in `foreman/dashboard_service.py` calls
`ForemanStore` methods:
- `list_projects()`, `get_project()`
- `list_sprints()`, `get_sprint()`, `get_active_sprint()`
- `list_tasks()`, `get_task()`
- `list_runs()`, `list_events()`
- `task_counts()`, `run_totals()`, `task_run_totals()`

No separate read-model layer or projection tables exist. The JSON API endpoints serialize store results directly.

## Consequences

**Positive:**
- Simple implementation with no extra abstraction layers
- Dashboard always shows current SQLite state
- Reuses existing store methods with proven test coverage

**Negative:**
- Dashboard API is coupled to store schema
- Complex dashboard queries may require new store methods
- No caching or pre-aggregation for expensive queries

**Future considerations:**
- If dashboard performance degrades, consider adding read-model projections
- If dashboard needs real-time updates, the store boundary remains valid but transport changes (polling → streaming)
- The approved boundary does not block future introduction of a dedicated query layer

## References

- `foreman/dashboard_service.py` — store-backed dashboard service methods
- `foreman/store.py` — ForemanStore read methods
- `docs/mockups/foreman-mockup-v6.html` — UI hierarchy reference
