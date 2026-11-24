# PR Summary: fix/engine-one-task-at-a-time

## Summary

- **The engine runs one task at a time** (ADR-0039). The owner, on
  2026-11-24: "Either sequential or parallel but this faux parallelism makes
  no sense", then "Yes, do it by hand".
- **A task waiting at a gate holds the queue.** While a task of the active
  sprint is stopped there for a user's decision, the pass starts no other
  task. It ends `waiting_for_decision`, and a resident engine waits for the
  decision, which wakes it. The decided task is then carried on first. The
  next task starts from the default branch it left, so tasks run by the
  engine no longer collide with each other on shared files.
- **The side door is removed.** It merged approved tasks inside another
  task's agent step (ADR-0011's 2026-11-15 amendment, withdrawn).
  `_carry_out_approved_merges`, `only_roles`, `MERGE_STEP_ROLES` and
  `APPROVED_MERGE_CHECK_SECONDS` are gone.
- **Two cases are unchanged.** A task blocked by a failure does not hold the
  queue. A request to run a named task still runs it.

## Scope

- `foreman/engine/orchestrator/passes.py`: `_task_waiting_for_a_decision`,
  checked before each new task; the side door removed.
- `foreman/engine/orchestrator/base.py`, `foreman/engine/orchestrator/tasks.py`,
  `foreman/engine/workflow_runner/base.py`: `only_roles` and the side door's
  settings removed.
- `foreman/definitions/gate_steps.py`: `workflow_gate_steps`, the gate steps
  of a loaded workflow, used by `resolve_gate_steps` and by the pass.

## Files changed

- Code as above.
- Tests:
  - `tests/test_engine_one_task_at_a_time.py` (new);
  - `tests/test_engine_approved_merges.py` (removed with the side door);
  - `tests/test_engine_gates.py` and `tests/test_workflow_gates.py`: a pass
    stopped at a gate ends `waiting_for_decision`.
- Docs:
  - ADR-0039 and the ADR index;
  - ADR-0011 (amendment withdrawn);
  - spec §6.1, amended;
  - `docs/MANUAL.md`, `docs/ARCHITECTURE.md`.

  `CHANGELOG.md`, `docs/sprints/current.md` and `docs/sprints/backlog.md`
  are left alone on purpose. Sprint 62's queued tasks edit them, and this
  branch would make them collide. They are updated when the queue is empty.

## Migrations

None.

## Risks

- The engine waits while a user decides, idle. On 2026-11-24 approvals came
  within seconds to minutes. A project whose merges Foreman approves never
  stops at that gate.

## Tests

- `tests/test_engine_one_task_at_a_time.py`:
  - a task at its merge approval holds the queue, through repeated passes;
  - after the approval it is merged first, and the second task's branch
    starts from that merge;
  - a task blocked by a failure does not hold the queue.
- The whole Python suite before the merge; ruff and lint-imports.

## Acceptance criteria

- No task starts while another of the active sprint waits for a decision.
- A decided task is merged before the next task starts.
- No task's steps run inside another task's step.

## Follow-ups

When sprint 62's queue is empty:
- a CHANGELOG line;
- backlog entries:
  - "several tasks at once in one project", as a separate decision;
  - FOR-52's review saw the tests recorded at an older commit after they
    had run again at the current one, to look into.
