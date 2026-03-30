# Current Sprint

- Sprint: `sprint-02-orchestrator`
- Status: active
- Goal: move one persisted task through the standard development workflow using
  the SQLite store plus declarative role and workflow definitions
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Included tasks

1. `[todo]` Implement the orchestrator main loop
   Deliverable: one task can move through develop, review, test, merge, and
   done states using persisted store records.

2. `[todo]` Add built-in execution seams for the standard development workflow
   Deliverable: `_builtin:run_tests`, `_builtin:merge`, and
   `_builtin:mark_done` execute through explicit orchestrator paths rather than
   hard-coded workflow branching.

3. `[todo]` Add integration coverage for persisted workflow transitions
   Deliverable: tests prove reviewer feedback and test failures carry output
   back into development and honor workflow fallback behavior.

## Excluded from this sprint

- project scaffold generation from `foreman init`
- context projection into `.foreman/`
- native Claude Code and Codex runner implementations
- dashboard and monitoring CLI surfaces

## Acceptance criteria

- a project task can advance through the standard development workflow using
  persisted store state and loaded workflow definitions
- orchestrator transitions are driven by the loaded workflow graph rather than
  ad hoc branching
- built-in test, merge, and mark-done steps have explicit seams
- docs and validation remain good enough for a fresh autonomous agent to pick
  the next slice without extra human context

## Known risks

- bootstrap supervisor behavior could still drift from the eventual native
  orchestrator loop if the boundaries stay implicit
- merge and test built-ins touch git and process execution, so sandbox-safe
  seams matter before native runner work lands

## Demo checklist

- show the repo validation passing
- show `foreman roles` and `foreman workflows` responding
- show one integration test that advances a task through loaded workflow steps
