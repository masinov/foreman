# Current Sprint

- Sprint: `sprint-45-supervised-convergence-validation`
- Status: in_progress
- Branch: `fix/task-repair-first-live-supervised-run-defect`
- Started: 2026-04-22

## Goal

Run a fresh supervised backend session against current main, verify reviewed
supervisors reconcile approved merges into SQLite state, and fix the first
defect exposed by the live run.

## Context and rationale

Sprint-44 introduced the supervisor finalization seam and post-merge branch
safety. Sprint-45 validates that seam end to end by running the reviewed
supervisors and hardening the first defect they expose.

## Constraints

- backend-only
- do not manually edit `.foreman.db`
- keep branch ownership rules intact: developers work on feature branches,
  supervisors merge approved work

## Affected areas

- `tests/test_reviewed_claude.py` — new regression coverage for Claude supervisor
- `tests/test_supervisor_state.py` — additional backend edge cases
- `docs/sprints/current.md` — this sprint definition
- `docs/STATUS.md` — sprint and task status

## Tasks

- [done] Supervised reconciliation live validation seam (task-supervised-reconciliation-live-validation-seam)
  - Added `tests/test_reviewed_claude.py` with 22 tests covering:
    - completion marker detection (task and spec complete)
    - task ID extraction from multiple formats
    - reviewer decision parsing (APPROVE/DENY/STEER)
    - main violation detection (direct main branch, main HEAD change)
    - API failure tracking and reset
    - finalize_supervisor_merge integration (missing DB, none result, success payload)
  - Extended `tests/test_supervisor_state.py` with 2 new tests:
    - `test_finalize_supervisor_merge_skips_already_done_task` — no duplicate events
    - `test_finalize_supervisor_merge_does_not_complete_sprint_when_other_tasks_unresolved`
- [todo] Repair first live supervised run defect (task-repair-first-live-supervised-run-defect)
- [done] Reviewed Claude supervisor regression coverage (task-reviewed-claude-supervisor-regression-coverage)
  - Added 18 new tests in `tests/test_reviewed_claude.py` covering:
    - TASK_ID extraction edge cases: empty colon value, bold header with next-line
      value, body-text false positives, empty input, first-match wins
    - SQLite reconciliation: explicit task_id pass-through, missing DB error,
      none-result recovery prompt
    - Malformed completion summary rejection: whitespace-only normalize_decision,
      DENY without colon, empty string, STEER/DENY preserved as-is
    - Developer completion declaration false positives
    - Main violation detection: on-main branch, main-head change, empty main head
  - 40 tests pass total (32 in test_reviewed_claude, 8 in test_supervisor_state)

## Validation

- `./venv/bin/python -m pytest tests/test_supervisor_state.py tests/test_reviewed_codex.py tests/test_reviewed_claude.py -q`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
