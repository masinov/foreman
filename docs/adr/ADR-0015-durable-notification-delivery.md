# ADR-0015: Durable Notification Delivery

- Status: accepted
- Date: 2026-09-08
- Deciders: engine team

## Context

ADR-0014 makes `notification` a policy decision and stamps that decision on
events that may need to reach a person. A recorded decision is not delivery.
Calling a network service directly from the orchestrator would make task
progress depend on webhook latency and availability, lose failed attempts on a
restart, and leave no durable answer to whether an operator was notified.

Destinations also need credentials. Storing signing secrets in project
settings or a destination row would copy them into SQLite, backups,
diagnostics, and possibly UI responses.

## Decision

Notification delivery uses a durable outbox. Migration 18 adds:

- `notification_destinations`, scoped to a project and unique by project/name;
- `notification_deliveries`, one row for an event/destination pair, with its
  immutable JSON payload, attempt count, next attempt time, outcome, and last
  error.

The orchestrator's dispatcher examines only announceable persisted events and
the `notify` decision stamped on each event. It inserts at most one delivery
for each enabled destination. The insert is idempotent for the
event/destination pair and never performs network I/O.

A separate worker claims due rows, invokes a transport, and records the
result. `foreman serve` drains a bounded batch between engine passes. One-shot
`foreman run` performs a final bounded drain before returning. Failures use
exponential backoff from 30 seconds, capped at 30 minutes, with five attempts
by default. Exhaustion leaves the row in `failed` and emits
`notification.failed`; it never changes the originating task or run outcome.

The first transport is a generic JSON webhook. Payload schema `1.0` includes
the project, task when present, source event, notification kind, summary, and
occurrence time. Optional HMAC-SHA256 signing reads a key from the environment
variable named by `secret_env` at send time. SQLite stores the variable name,
not its value. Receivers get stable event, delivery, and signature headers.

The CLI owns destination setup and diagnosis through `foreman notify
add|list|remove|test|deliveries`. A test send is intentionally synchronous so
an operator gets an immediate configuration result; engine deliveries remain
asynchronous.

## Consequences

- A broken receiver cannot stall or fail task execution.
- Delivery state and errors survive engine restarts and are inspectable
  without parsing logs.
- Reconsidering an event after a restart cannot duplicate a destination's row.
- A project can fan one event out to multiple destinations independently.
- Operators must provide any configured signing environment variable to every
  process that may drain deliveries.
- The worker is currently single-process cooperative work in the resident
  loop; horizontal workers will require an atomic claim or lease.
- Removing a destination also removes its queued and historical delivery rows.
