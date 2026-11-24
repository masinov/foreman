# PR Summary: fix/task-foreman-init-and-settings-runners-use-the-projec

## Summary

- Settings › Runners lists the models roles use as each project resolves them (shipped, then the workspace's, then the project's own).
- `foreman init` accepts a workflow the workspace defines and keeps an existing project's workflow, whatever its source.

## Scope

- Sprint 62 slice 6, part: init and Runners. Both read definitions through `foreman.definitions.layers`, the layer the engine uses; nothing resolves definitions a second way.

## Files changed

- `foreman/services/access.py`, `foreman/api/routers/access.py`: `describe_runner_backends(store)`.
- `foreman/cli/projects.py`: `handle_init` uses `workspace_definitions` / `project_definitions`.
- `tests/test_dashboard_access_api.py`, `tests/test_cli.py`.
- `docs/MANUAL.md`, `CHANGELOG.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`.

## Migrations

- none

## Risks

- A project or workspace definition that no longer loads now makes `GET /runners` and `foreman init` fail with that error, as the engine does for that project.

## Tests

- Runners shows workspace- and project-only models and drops an unused shipped one.
- `init` with a workspace workflow, `init` again keeping a workspace or project workflow, unknown workflow still refused.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- All three; see Tests.

## Follow-ups

- Rest of slice 6 (manager replies, filed-task origin, one event stream, who finishes a sprint).
