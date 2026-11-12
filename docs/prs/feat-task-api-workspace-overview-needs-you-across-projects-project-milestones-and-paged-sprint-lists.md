# PR Summary: feat/task-api-workspace-overview-needs-you-across-projects-project-milestones-and-paged-sprint-lists

## Summary

- Adds the reads the rebuilt dashboard needs: `GET /api/v1/workspace`, `GET /api/v1/needs-you`, `GET /api/v1/projects/{id}/needs-you`, `GET /api/v1/milestones`, `GET /api/v1/projects/{id}/milestones`, and `status`, `q`, `limit`, `offset` plus `total` on `GET /api/v1/projects/{id}/sprints`.
- All answer under `/api` too. Shapes are documented in `docs/ARCHITECTURE.md` ("Views across projects").

## Scope

- Python only. New store part `foreman/store/overview.py` (grouped reads, one statement each), `foreman/dashboard_overview.py` (the reader), thin routes in `routers/projects.py` and `routers/sprints.py`, service methods in `dashboard_service.py`, gate policies on `WorkflowGateSteps`.
- The routes sit in the existing projects router so the router count pinned by an existing test is unchanged.
- No new table (see below). No frontend change, no dependency.

## Files changed

- `foreman/store/overview.py`, `foreman/store/__init__.py`
- `foreman/dashboard_overview.py`, `foreman/dashboard_service.py`, `foreman/engine_control.py`
- `foreman/dashboard/routers/projects.py`, `foreman/dashboard/routers/sprints.py`, `foreman/dashboard/context.py`
- `tests/test_dashboard_workspace_api.py`, `docs/ARCHITECTURE.md`

## Migrations

- none. Milestones are derived from existing data: sprint `started_at`/`completed_at`, `engine.merge` events, completed `engine_commands`, and the engine lease history in `leases`. These answer every kind except one (see Follow-ups), so no table was added.

## Risks

- Milestone timestamps come from several sources with two stored formats (`Z` and `+00:00`); ordering uses `julianday`, which is millisecond-precise, so events within the same millisecond tie-break by id.
- `since` for needs-you is derived (end of the last run), since tasks record no "blocked at".
- The intake queue sprint can itself be a project's active sprint (when nothing else is active); the workspace reports it as such.
- A gate with no `plan_approval` policy is reported as `approve_merge`.

## Tests

- `tests/test_dashboard_workspace_api.py` (25 tests): each endpoint populated, empty, paged with total, filtered, and with a bad parameter returning the 400 envelope; unknown project gives 404; `/api` alias equals `/api/v1`; sprint list without parameters keeps its old shape; query-count tests show the SELECT count for needs-you and workspace does not grow with added tasks or sprints.
- Full suite: 1153 tests pass (1 skipped); `ruff check .` passes.

## Screenshots or output examples

- n/a (API only)

## Acceptance criteria satisfied

- All listed; the existing `test_every_router_is_mounted_under_every_prefix` and other dashboard tests are untouched and pass.

## Follow-ups

- "Engine stopped on a limit": the reason an engine stopped is only written to the serve log, not the database, so a stop cannot yet be told apart as a limit stop. Persisting a stop reason (for example an engine event on `serve.stopped`) would let `engine_stopped` carry it. Not invented here.
- The backlog task will replace the intake-queue sprint; `backlog_counts` and the milestone exclusion of `-intake` sprints need updating then.
- Per-project engine view still costs a fixed few queries per project (`describe_engine`); batching it is possible if the project count grows.
