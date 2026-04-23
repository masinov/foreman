# PR Summary: feat/task-backend-guard-for-weak-completions

## Summary

Recover the interrupted sprint-46 backend-guard task and wire completion
guarding into the shipped workflow at the correct boundary: `_builtin:merge`,
not `_builtin:mark_done`.

## Scope

This branch turns the completion-evidence model into an actual backend guard
for implementation tasks. The guard now evaluates branch diff evidence before
merge and blocks only when the task branch has no material changes or only
docs/tests changes. It also preserves the specific blocked reason in
orchestrator state so operators can see why a task stopped.

## Files changed

- `foreman/builtins.py`
  - move the completion guard to `_builtin:merge`
  - restore `_builtin:mark_done` to a simple terminal success step
  - block only `feature`, `fix`, and `refactor` tasks when branch evidence is
    empty or docs/tests-only
- `foreman/orchestrator.py`
  - preserve builtin `blocked` detail instead of collapsing it into the generic
    unhandled-outcome fallback
- `tests/test_orchestrator.py`
  - add merge-time regression coverage for weak-completion blocking and
    successful implementation-task completion
  - repair stale expectations from the abandoned mark-done design
- `docs/STATUS.md`
  - update active-branch status for the recovered task branch
- `docs/sprints/current.md`
  - update sprint-46 task state and validation notes

## Migrations

- none

## Risks

- the current guard is intentionally narrow and heuristic-based; it only checks
  for empty branch evidence or docs/tests-only changes
- tasks with legitimate non-code deliverables should continue to use
  non-implementation task types (`docs`, `chore`, `spike`) so they are not
  subject to the implementation-task guard
- the interrupted live run still needs SQLite reconciliation so Foreman no
  longer thinks the dead developer run is active

## Tests

- `./venv/bin/python -m pytest tests/test_orchestrator.py -q`
- `./venv/bin/python -m pytest tests/test_store.py tests/test_executor.py tests/test_roles.py -q`

## Output examples

- implementation task with branch changes like `feature.txt` and `ready.txt`
  now completes through `merge -> done`
- implementation task with only docs/tests changes now blocks at merge with a
  specific reason instead of flowing to terminal completion

## Acceptance criteria satisfied

- [x] weak-completion guard runs before terminal completion
- [x] valid implementation tasks no longer block after successful merge
- [x] docs/tests-only implementation branches are blocked with a specific reason
- [x] builtin `blocked` reasons survive orchestrator outcome handling
- [x] branch-specific repo-memory summary added

## Follow-ups

- reconcile the stale interrupted run in `.foreman.db` and reset the task to a
  coherent resumable state
- continue sprint 46 with reviewer prompt hardening and completion-truth docs
- validate the repaired branch in a fresh supervised Foreman run after the task
  state is reset
