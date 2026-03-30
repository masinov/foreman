# PR Summary: feat/human-gate-resume

## Summary

- Implemented human-gate resume functionality allowing operators to approve or deny
  paused tasks through `foreman approve <task-id>` and `foreman deny <task-id>` CLI commands.
- Tasks paused at `_builtin:human_gate` steps now resume from their persisted workflow
  state with carried output and decision history.

## Scope

- `foreman/orchestrator.py` — added `HumanGateResumeResult` dataclass and
  `resume_human_gate` method for resuming paused tasks
- `foreman/cli.py` — added `handle_approve`, `handle_deny`, and shared
  `_handle_human_gate_decision` handlers with `--db` (required) and `--note` options
- `tests/test_orchestrator.py` — added `HumanGateResumeTests` class with 4 test methods

## Files changed

- `foreman/orchestrator.py`
- `foreman/cli.py`
- `tests/test_orchestrator.py`
- `docs/sprints/current.md`

## Tests

- `HumanGateResumeTests.test_human_gate_pause_blocks_task` — verifies tasks pause at
  human_gate steps with blocked status
- `HumanGateResumeTests.test_approve_resumes_to_next_step` — verifies approve outcome
  transitions to the next workflow step
- `HumanGateResumeTests.test_deny_loops_back_with_carry_output` — verifies deny outcome
  loops back with carried output preserved
- `HumanGateResumeTests.test_resume_non_human_gate_task_raises` — verifies error on
  non-human-gate tasks

All 19 tests pass (6 ForemanOrchestratorTests + 4 HumanGateResumeTests + 9 CLI tests).

## Screenshots or output examples

```
$ foreman approve task-001 --db foreman.db
Approved task
Database: foreman.db
Task ID: task-001
Resume from: human_approval
Next step: develop
Status: in_progress
Resume deferred: no
```

## Acceptance criteria satisfied

- [x] `foreman approve` and `foreman deny` operate on paused human-gate tasks
- [x] Paused tasks resume from persisted workflow state instead of restarting
- [x] Approval and denial decisions are persisted with workflow and event history
- [x] Docs and validation remain good enough for a fresh autonomous agent

## Follow-ups

- Native runner implementations will enable non-deferred resume execution
- Monitoring CLI surfaces (`foreman board`, `foreman watch`) for human-gate visibility
