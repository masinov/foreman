# Backlog

## Tier 3 — Architecture / spec gaps (remaining)

### SSE transport hardening (deferred)

The sprint SSE stream loop polls SQLite directly inside the FastAPI async
generator on a 500 ms interval. This works but is not a final transport design.
Fixing it requires an in-process pub/sub layer (e.g. asyncio queue or
`anyio.Event`) so the generator wakes on a write rather than polling.

- Effort: medium–large
- Urgency: low — current polling is acceptable under normal load
- Prerequisite: decide whether to use an in-process bus or a lightweight broker

## Parking lot

- E2E test coverage for features added in sprints 32–35 (task editing,
  deletion, sprint ordering, date display)
- E2E test coverage for meta agent panel (sprint-40)
- Persist meta agent session history to SQLite (survives server restarts)
- Task `order_index` editing UI within a sprint board (reorder tasks within a
  sprint, similar to sprint ↑/↓ reorder)
- Task priority UI (priority field exists in schema and drawer display but has
  no edit affordance)
- Move task between sprints (no service method or UI; requires task reassignment
  to a different `sprint_id`)
- Codex cost capture — `cost_usd` currently persists as `0.0`; needs Codex
  app-server contract to expose USD pricing
- Run and prompt retention product-level defaults — currently require explicit
  project settings; old runs accumulate if neither is set
