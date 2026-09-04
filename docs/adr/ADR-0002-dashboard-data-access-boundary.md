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

## Amendment (sprint 54): control goes through the command table

The original decision covered *reads*. Writes that steer the engine were left
to the dashboard's own devices, and it grew a module-level `dict` of
`foreman run` subprocess handles: Start spawned a process, Stop terminated the
handle and flipped every in-progress task to `blocked`, and "is the agent
running" meant "is that handle alive".

That does not survive the resident engine. A `foreman serve` started from a
terminal, from a different dashboard process, or on another machine is
invisible to a dict in one web process; a killed process leaves tasks marked
blocked for a reason the engine never gave; and a dashboard that restarts
loses its idea of what is running while the engine keeps working.

**The dashboard controls the engine only through the `engine_commands` table.**

- Reads stay as decided: `ForemanStore` directly, now including the engine
  lock view and the command log, with derivations shared with the CLI in
  `foreman/engine_control.py` so the two surfaces cannot disagree.
- Writes that steer the engine are command rows — `resume`, `pause`,
  `run_task`, `stop_task` — each recording who asked. The dashboard never
  changes task status to express an operator intention about the engine; the
  engine owns those transitions.
- The dashboard holds no process handles. The one process it may start is a
  detached `foreman serve` when no engine is resident on a project, through an
  injectable spawner, because there is otherwise nobody to send a command to.
  It keeps no handle on the result and cannot stop it except by command.

Consequence: an action returns as soon as the command is durably queued, not
when the engine has acted on it. The UI reports engine state (resident,
paused, not running, with heartbeat age) and the command log, so a queued
order that has not landed yet is visible rather than silently assumed.

## References

- `foreman/dashboard_service.py` — store-backed dashboard service methods
- `foreman/engine_control.py` — engine state and dead-letter derivations shared
  with the CLI
- `docs/MANUAL.md` §17 (Run/Pause, dead-letter kinds) and §23 (the command
  table)
- `foreman/store.py` — ForemanStore read methods
- `docs/mockups/foreman-mockup-v6.html` — UI hierarchy reference
