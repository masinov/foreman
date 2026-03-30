# Sprint Archive: sprint-05-human-gates

- Sprint: `sprint-05-human-gates`
- Status: completed
- Goal: resume paused human-gate tasks through `foreman approve` and
  `foreman deny` with persisted workflow state
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Final task statuses

1. `[done]` Add CLI commands for human-gate approval and denial
   Deliverable: operators can issue `foreman approve <task-id>` and
   `foreman deny <task-id>` against paused tasks in the SQLite store.

2. `[done]` Integrate workflow resume semantics for paused tasks
   Deliverable: a task paused by `_builtin:human_gate` can resume from its
   persisted workflow step with the recorded carried output and decision.

3. `[done]` Add coverage for pause, approve, deny, and resume behavior
   Deliverable: tests prove human-gate tasks block, persist resume metadata,
   and continue through the workflow after an explicit human decision.

## Deliverables

- `foreman approve --db <path>` and `foreman deny --db <path>`
- persisted human-decision runs plus `workflow.resumed` events
- immediate resume for executor-backed orchestrator calls
- deferred next-step persistence for CLI-driven resume before native runners
- orchestration and CLI coverage for approve, deny, and deferred resume

## Demo notes

- `./venv/bin/python -m unittest tests.test_orchestrator tests.test_cli -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/foreman approve --help`
- `./venv/bin/foreman deny --help`

## Follow-ups moved forward

- `sprint-06-claude-runner`: implement the first native Claude Code runner so
  agent-backed workflow steps can execute without deferred bootstrap behavior
- backlog: native Codex runner, monitoring CLI, dashboard implementation, and
  the first ADR once runner contracts harden
