# PR Summary: refactor/layers-services

## Summary

- Slice 4 of ADR-0032. `DashboardService` becomes eleven services, one per
  area, in `foreman/services/`. The `dashboard_*` root modules and `backlog`
  join them, and `foreman/dashboard/` becomes `foreman/api/`. No behaviour
  or API change.

## Scope

- `foreman/services/`: `base.Service` (store, clock, finding a record,
  requester, mutations, gate steps) and `ProjectService`, `EngineService`,
  `SprintService`, `TaskService`, `BacklogService`, `IntakeService`,
  `ProposalService`, `DecisionGateService`, `WorktreeService`,
  `DefinitionService`, `WorkspaceService`, put together by `Services`. A
  service that uses another is given it in its constructor.
- Errors: `services/errors.py` (`ServiceError`, `NotFoundError`,
  `InvalidRequestError`, `ActionFailedError`, `UnauthenticatedError`,
  `ForbiddenError`), renamed from `Dashboard*Error` because they are not the
  dashboard's.
- `services/views.py`: the serializers more than one service uses
  (`stable_slug`, `serialize_engine_state`, `task_source`).
- `foreman/api/`: the old `dashboard/` package, plus `guard`, `runtime`
  (the bind, the security posture, the server) and `assets` (the frontend
  bundle), which was split out of `runtime` so `runtime` imports `app` and
  not the reverse. `assets` finds the bundle and the frontend source from
  its own place in the package. The import shim `dashboard_backend` is
  deleted; uvicorn's reload target is `foreman.api.app`.
- `services/task_models.py` (was `dashboard/task_models.py`): the shape of
  the task reads, which the services build.
- Every route and test calls the owning area
  (`api.tasks.accept_task(...)`), rewritten by a script from the method's
  area.

## Files changed

- `foreman/services/*`, `foreman/api/*`, `foreman/cli/engine.py`,
  `foreman/cli/monitor.py`, `.importlinter` (`api`, `services`), the tests
  that call the service, ADR-0032, `docs/ARCHITECTURE.md`, `docs/MANUAL.md`,
  `README.md`, `docs/ROADMAP.md`, `docs/sprints/current.md`, `CHANGELOG.md`.

## Migrations

- none

## Risks

- `foreman/services/sprints.py`, `tasks.py` and `engine.py` are still 350
  to 500 lines. Each is one area, and they are no longer one class.
- Restart the dashboard after the merge. A process started from the old
  tree has `foreman.dashboard_backend` as its reload target.

## Tests

- full Python suite, ruff, `lint-imports`, repo-memory validation.

## Acceptance criteria satisfied

- No `dashboard_` module is left at the root, and the API and services are
  their own layers in the contract.

## Follow-ups

- Slice 5: `notifications/` by concern, the remaining in-function imports,
  the end-state docs.
