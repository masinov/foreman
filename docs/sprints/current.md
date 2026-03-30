# Current Sprint

- Sprint: `sprint-08-monitoring-cli`
- Status: active
- Goal: expose project state through CLI inspection commands
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Included tasks

1. `[done]` Implement `foreman board` command
   Deliverable: operators can view sprint and task status without opening the database.

2. `[done]` Implement `foreman watch` command
   Deliverable: live activity feed showing task progress, agent messages, and cost updates.

3. `[done]` Implement `foreman history` command
   Deliverable: run history with events, decisions, and outcomes.

4. `[done]` Implement `foreman cost` command
   Deliverable: cost summary by project, sprint, or task.

## Excluded from this sprint

- dashboard implementation
- ADR framework work
- multi-project support

## Acceptance criteria

- all four commands work with `--db` flag
- operators can inspect state without opening the database
- docs and validation remain good for a fresh autonomous agent

- live updates visible in watch output
- history shows decisions and outcomes chronologically
- cost tracking works across projects, sprints, and tasks

- demo checklist
- show `foreman board` output for a sample project
- show `foreman watch` with live updates
- show repo validation passing after the slice lands
