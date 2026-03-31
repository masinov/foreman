# Current Sprint

- Sprint: `sprint-28-autonomous-task-selection`
- Status: done
- Goal: implement `task_selection_mode="autonomous"` in the orchestrator so the
  engine can create and execute tasks without human task assignment
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/orchestrator.py`
  - `tests/test_orchestrator.py`

## Included tasks

1. `[done]` Implement `_select_next_task_autonomous()` in `ForemanOrchestrator`
   Deliverable: `select_next_task()` dispatches to `_select_next_task_autonomous()`
   for `task_selection_mode="autonomous"` projects; resumes in-progress tasks
   first, then creates placeholder tasks persisted to SQLite with
   `created_by="orchestrator"`; returns `None` when the per-sprint
   `max_autonomous_tasks` limit (default 5) is reached or no active sprint exists.

2. `[done]` Write regression tests
   Deliverable: 8 new tests in `AutonomousTaskSelectionTests` covering placeholder
   creation, in-progress resume, no-sprint, limit enforcement (custom and
   default), human-task exclusion from limit count, directed-mode unchanged, and
   unknown-mode error.

3. `[done]` Update all repo-memory docs
   Deliverable: `docs/STATUS.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
   `docs/sprints/current.md`, `docs/sprints/backlog.md`, `CHANGELOG.md`, and
   sprint archive written.

## Excluded from this sprint

- `foreman db migrate` CLI surface
- autonomous agent execution integration (depends on a live agent runner in test
  context)

## Acceptance criteria

- `select_next_task()` returns a placeholder task for an autonomous project with
  an active sprint and no in-progress task
- `select_next_task()` resumes an in-progress task before creating a new one
- limit is enforced: returns `None` when `max_autonomous_tasks` orchestrator
  tasks exist in the sprint
- directed mode and unknown-mode error paths are unchanged
- 8 new tests pass; full non-E2E suite (204 tests) passes with no regressions
