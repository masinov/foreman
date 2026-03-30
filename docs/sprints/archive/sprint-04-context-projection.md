# Sprint Archive: sprint-04-context-projection

- Sprint: `sprint-04-context-projection`
- Status: completed
- Goal: project runtime context from SQLite into `.foreman/context.md` and
  `.foreman/status.md` before and after workflow activity
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Final task statuses

1. `[done]` Implement store-driven context rendering for project, sprint, and
   task state
   Deliverable: Foreman can render `.foreman/context.md` and
   `.foreman/status.md` from persisted SQLite records without treating those
   files as committed project state.

2. `[done]` Integrate automatic context projection into orchestrator lifecycle
   and `_builtin:context_write`
   Deliverable: the orchestrator writes fresh context before agent runs and
   after task completion, and workflows can explicitly invoke the same
   projection path through `_builtin:context_write`.

3. `[done]` Add coverage for context projection and runtime updates
   Deliverable: tests prove projected files reflect active sprint and task
   state and remain under the gitignored `.foreman/` directory.

## Deliverables

- `foreman.context` runtime context rendering and write helpers
- orchestrator-managed context refresh before agent steps and after task
  completion
- `_builtin:context_write` support for explicit workflow-driven projection
- context projection unit coverage plus orchestrator integration tests

## Demo notes

- `./venv/bin/python -m unittest tests.test_context tests.test_orchestrator -v`
- `./venv/bin/python -m unittest discover -s tests -v`

## Follow-ups moved forward

- `sprint-05-human-gates`: add `foreman approve` and `foreman deny` with
  persisted resume semantics
- backlog: native runners, monitoring CLI, dashboard implementation, and the
  first ADR once human-gate or runner contracts harden
