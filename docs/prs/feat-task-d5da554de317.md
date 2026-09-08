# PR Summary: feat/task-d5da554de317

## Summary

FOR-12 closes the gap between the notification policy recorded by ADR-0014
and an operator actually receiving it. Policy-selected attention requests,
human gates, and task completions now fan out to project webhook destinations
through a durable delivery queue. Network failures cannot fail or hold open the
task that produced the event.

For example, a human merge gate previously produced only a
`workflow.paused` event with `notify=attention`. It now also creates one
pending row per enabled destination. The resident worker sends those rows,
records the response or error, and retries failures without replaying the
workflow event.

## Scope

- Migration 18, destination and delivery models, and store operations.
- Canonical policy-matrix resolution, including task overrides and task-type
  rules.
- Event dispatcher and durable delivery worker.
- Generic JSON webhook transport with optional headers and HMAC-SHA256 signing.
- Bounded retry scheduling and terminal failure events.
- Resident-engine and one-shot-engine draining.
- `foreman notify add|list|remove|test|deliveries`.
- Architecture, operator, sprint, status, and release documentation.

## Files changed

- `foreman/notifications.py`: policy mapping, payload contract, dispatcher,
  worker, validation, and webhook transport.
- `foreman/migrations.py`, `foreman/models.py`, `foreman/store.py`: migration
  18 and persistence boundary.
- `foreman/orchestrator.py`, `foreman/serve.py`, `foreman/builtins.py`: queue
  and drain integration.
- `foreman/cli.py`, `foreman/logs.py`: operator commands and log severity.
- `tests/test_notifications.py`, `tests/test_intake.py`: focused and
  integration coverage.
- `README.md`, `CHANGELOG.md`, `docs/STATUS.md`, `docs/MANUAL.md`,
  `docs/ARCHITECTURE.md`, `docs/sprints/current.md`, and ADR indexes.
- `docs/adr/ADR-0015-durable-notification-delivery.md`: durable delivery
  decision.

## Migrations

Migration 18 creates `notification_destinations` and
`notification_deliveries`. Both cascade with their project; delivery rows also
cascade with their destination. A uniqueness constraint on source event and
destination makes dispatch idempotent.

## Risks

- The current worker is cooperative in a single resident process. Running
  multiple delivery workers against one database would require an atomic claim
  lease before horizontal delivery is safe.
- A synchronous webhook may consume up to its ten-second timeout. Batch size is
  bounded at 20, but a set of hanging destinations can lengthen the interval
  between engine passes. It cannot change a task outcome.
- Signing depends on the configured environment variable being present in the
  process that drains the queue. A missing key becomes a visible retry/failure,
  while the key itself is never persisted.
- Removing a destination cascades its pending and historical deliveries. The
  CLI states this before and after the operation; longer-lived audit retention
  would need destination tombstones instead.

## Tests

```text
./venv/bin/python -m unittest discover -s tests
Ran 983 tests in 76.958s — OK (skipped=1)

npm --prefix frontend test
48 tests in 4 files — passed

npm --prefix frontend run build
production bundle built
```

`tests/test_notifications.py` covers policy precedence, schema upgrade,
destination CRUD, idempotent fan-out, event filtering, payload shape, webhook
headers and signatures, timeouts and response failures, retry scheduling,
terminal failure events, exception isolation, resident and one-shot drains,
and all CLI operations. No test contacts a real webhook.

## Output example

```console
$ foreman notify add foreman --name ops --url https://hooks.example/foreman \
    --secret-env FOREMAN_WEBHOOK_SECRET
Notification destination added
Project: foreman | Foreman
Destination: dst-… | ops (webhook)
Signed: FOREMAN_WEBHOOK_SECRET
Policy: notification=attention

$ foreman notify deliveries foreman --status failed
Notification deliveries
Project: foreman | Foreman
- none
```

## Acceptance criteria satisfied

- Policy-selected events reach configured destinations asynchronously.
- Delivery is durable, idempotent, retryable, inspectable, and isolated from
  task execution.
- Secrets are referenced from the environment rather than stored.
- Both autonomous entry points drain the same queue.
- Operators can configure, test, inspect, and remove destinations.

## Follow-ups

- Add an atomic delivery claim before supporting multiple delivery workers.
- Add transports behind the existing transport protocol when a concrete chat
  or email provider is selected.
- Decide whether destination removal needs retained delivery tombstones for a
  longer audit window.
