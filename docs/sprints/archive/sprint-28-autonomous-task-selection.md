# Sprint 28: Autonomous Task Selection

- Sprint: `sprint-28-autonomous-task-selection`
- Status: done
- Branch: `feat/autonomous-task-selection`
- Goal: implement `task_selection_mode="autonomous"` in the orchestrator so the
  engine can create and execute tasks without human task assignment

## Summary

Replaced the `OrchestratorError` stub in `select_next_task()` with a live
dispatch to `_select_next_task_autonomous()` for autonomous projects.  The new
method follows spec §6.2: it resumes an in-progress task if one exists, and
otherwise creates a new placeholder task (`title="[autonomous] new task"`,
`created_by="orchestrator"`) persisted to SQLite for the agent to populate via
the existing `signal.task_started` handler.  A per-sprint
`max_autonomous_tasks` safety bound (default 5, overridable in project
settings) prevents unbounded placeholder creation.

## Deliverables

- `_select_next_task_autonomous(project)` in `foreman/orchestrator.py`
- `_MAX_AUTONOMOUS_TASKS_DEFAULT = 5` class constant
- `select_next_task()` dispatches on `selection_mode == "autonomous"` before
  the directed path; unknown modes still raise `OrchestratorError`
- 8 new tests in `AutonomousTaskSelectionTests` in `tests/test_orchestrator.py`

## Files changed

- `foreman/orchestrator.py` — added `_select_next_task_autonomous()` and updated
  `select_next_task()` dispatch
- `tests/test_orchestrator.py` — added `AutonomousTaskSelectionTests`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/STATUS.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `CHANGELOG.md`

## Tests

- 8 new tests in `AutonomousTaskSelectionTests`
- 204 non-E2E tests pass total; no regressions

## Risks

- The agent must emit `signal.task_started` to populate placeholder tasks;
  if the first workflow step does not emit this signal, the task remains with
  the default title — this is the agent's responsibility per spec §6.2
- `max_autonomous_tasks` counts all tasks in the sprint with
  `created_by="orchestrator"`; tasks that finish (status `done`) still count
  toward the limit, so the limit bounds total autonomous work per sprint not
  concurrency

## Follow-ups

- `foreman db migrate` CLI surface for schema inspection
