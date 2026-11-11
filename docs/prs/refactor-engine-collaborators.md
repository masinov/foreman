# refactor/engine-collaborators

## Summary

Sprint 57 slice 2b. The orchestrator composes collaborators from
`foreman/engine/`, and its step loop reads as a sequence of named phases.

## Scope

New modules, each a class that takes exactly what it uses:

| Module | Class | Was |
|---|---|---|
| `task_writes.py` | `TaskWrites` | `_save_task`, `_adopt_operator_changes` |
| `retention.py` | `Retention` | `prune_old_history` and helpers |
| `sprints.py` | `SprintFlow` | sprint activation, advance, events |
| `recovery.py` | `Recovery` | orphaned tasks, stale runs, lease liveness |
| `selection.py` | `TaskSelector` | directed and autonomous selection |
| `signals.py` | `SignalHandler` | agent event persistence, signal handling |
| `agent_step.py` | `AgentStepRunner` | guarded execution, native runner step |
| `prompts.py` | `PromptBuilder` | `_build_prompt` |
| `task_worktrees.py` | `TaskWorktrees` | worktree ensure, reclaim, preflight |
| `coerce.py` | functions | payload coercion helpers |

`ForemanOrchestrator` keeps `select_next_task`, `recover_orphaned_tasks` and
`build_completion_evidence` as public entry points that delegate.

The step loop: the pre-step checks, the three kinds of step, the post-step
record and the transition are methods. The seven places that created a
blocked system run, emitted an event and parked the task are one
`_block_at_step`. The method bodies are the original text, moved.

## Files changed

`foreman/orchestrator.py`, ten new `foreman/engine/` modules, tests updated
to the new call paths, changelog, sprint.

## Migrations

None.

## Risks

- Two details of the loop were restated instead of moved: a limit no longer
  releases the lease at the point of blocking (the release after the loop
  covers every blocked exit, as before), and the "no transition" exit always
  returns through one path. The suite covers both.
- A blanket rename inside the moved step bodies changed a keyword argument
  name; the suite caught it (every engine test failed) and it is fixed.

## Tests

Full Python suite (1064 tests) and `ruff check`.

## Acceptance criteria satisfied

Slice 2b as written in `docs/sprints/current.md`.

## Follow-ups

Slice 2c.
