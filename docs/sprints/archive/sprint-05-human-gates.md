# Sprint Archive: sprint-05-human-gates

- Sprint: `sprint-05-human-gates`
- Status: complete
- Goal: resume paused human-gate tasks through `foreman approve` and
  `foreman deny` with persisted workflow state
- Completed: 2026-03-30

## Completed tasks

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

- `foreman/orchestrator.py` — `HumanGateResumeResult` dataclass and
  `resume_human_gate` method
- `foreman/cli.py` — `foreman approve` and `foreman deny` commands
- `tests/test_orchestrator.py` — `HumanGateResumeTests` class

## Branch

- `feat/human-gate-resume` → merged to main
