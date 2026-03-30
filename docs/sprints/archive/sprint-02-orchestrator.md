# Sprint Archive: sprint-02-orchestrator

- Sprint: `sprint-02-orchestrator`
- Status: completed
- Goal: move one persisted task through the standard development workflow using
  the SQLite store plus declarative role and workflow definitions
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Final task statuses

1. `[done]` Implement the orchestrator main loop
   Deliverable: one task can move through develop, review, test, merge, and
   done states using persisted store records.

2. `[done]` Add built-in execution seams for the standard development workflow
   Deliverable: `_builtin:run_tests`, `_builtin:merge`, and
   `_builtin:mark_done` execute through explicit orchestrator paths rather than
   hard-coded workflow branching.

3. `[done]` Add integration coverage for persisted workflow transitions
   Deliverable: tests prove reviewer feedback and test failures carry output
   back into development and honor workflow fallback behavior.

## Deliverables

- `foreman.orchestrator` driving the shipped development workflow from
  persisted tasks, runs, and events
- explicit built-ins for tests, merge, mark-done, and human-gate pause
- git execution helpers for branch checkout, merge, status, diff, and recent
  commit context
- orchestrator integration tests covering happy-path execution, carry-output
  loops, fallback blocking, and dependency-aware selection

## Demo notes

- `./venv/bin/python -m unittest discover -s tests -p 'test_orchestrator.py' -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/foreman roles`
- `./venv/bin/foreman workflows`

## Follow-ups moved forward

- `sprint-03-scaffold`: implement `foreman init` and repo scaffold generation
- backlog: context projection, human-gate resume commands, native runners,
  monitoring CLI, and dashboard implementation
