# refactor/api-handlers-off-loop

## Summary

Sprint 57 slice 6b: API handlers leave the event loop, write routes get typed
bodies, and a project gets one event stream.

## Scope

- Handlers: every route that does not stream is a plain `def`, which FastAPI
  runs on its thread pool. A JSON body arrives through
  `Depends(read_json_body)` or `Depends(body_as(Model))`, so the JSON
  content-type requirement (ADR-0016) is unchanged. The three streaming
  routes stay `async`.
- `foreman/dashboard/schemas.py`: `ProjectCreate`, `SprintCreate`,
  `TaskCreate`, `RequestedBy`, `AgentStart`, `TaskDenial`, `GuidanceNote`,
  `GateCreate`, `GateResolution`; strict types, unknown fields ignored,
  required-ness left to the service. Settings, task-field and role updates
  stay dicts.
- `foreman/dashboard/streaming.py`: `event_stream_response`, used by the
  sprint stream and the new `GET /projects/{id}/stream`.
- `DashboardService.list_project_stream_messages`.

## Files changed

`foreman/dashboard/routers/*.py`, `schemas.py` and `streaming.py` (new),
`foreman/dashboard_service.py`, `tests/test_dashboard_api.py`, changelog,
sprint.

## Migrations

None.

## Risks

- Types are strict: a client that sent a number where a string is expected
  is now refused where it used to be coerced.
- Each request already opened its own store connection, so moving handlers
  to threads adds no shared state.

## Tests

Full Python suite and `ruff check`.

## Acceptance criteria satisfied

Slice 6b as written in `docs/sprints/current.md`, without response models
and list pagination.

## Follow-ups

Response models and list pagination, shaped by what the rebuilt frontend
needs.
