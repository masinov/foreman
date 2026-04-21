# Current Sprint

- Sprint: `sprint-44-supervisor-state-reconciliation`
- Status: in_progress
- Branch: `fix/run-auto-activate-planned-sprint`
- Started: 2026-04-22

## Goal

Make supervised Foreman runs update SQLite state consistently with what the
supervisor actually did, so task completion, sprint completion, and queue state
in `.foreman.db` stay aligned with git history and repo docs.

## Context and rationale

The first supervised run was able to merge a branch into `main`, but the live
SQLite state still showed stale blocked tasks and an old active sprint. The
reviewed Codex supervisor also allowed follow-up work to continue on `main`
after the supervisor merge commit, which made the session appear cleaner than
it really was.

This sprint closes that backend gap by introducing an explicit supervisor
finalization seam for merged tasks and by blocking post-merge drift on `main`
inside the reviewed Codex wrapper.

## Constraints

- backend-only
- do not manually edit `.foreman.db`
- keep branch ownership rules intact: developers work on feature branches,
  supervisors merge approved work
- avoid duplicating sprint lifecycle logic inside the wrapper scripts

## Affected areas

- `foreman/store.py` — task lookup by branch
- `foreman/orchestrator.py` — shared supervisor merge finalization
- `foreman/supervisor_state.py` — wrapper-facing SQLite reconciliation seam
- `scripts/reviewed_codex.py` — persist completion and block post-merge work on `main`
- `scripts/reviewed_claude.py` — persist completion after supervisor merge
- `tests/test_reviewed_codex.py` — supervisor regression coverage
- `tests/test_supervisor_state.py` — backend reconciliation coverage
- `docs/STATUS.md` — active branch and sprint note
- `docs/sprints/current.md` — current sprint definition

## Implementation plan

### Task 1 — Shared finalization seam

Add one backend helper that maps a merged feature branch back to a tracked
project task, marks that task done, and resolves sprint lifecycle state through
Foreman code rather than raw supervisor-side SQLite writes.

### Task 2 — Reviewed supervisor wiring

Call the shared finalization seam from both reviewed supervisors immediately
after a successful merge. Carry an explicit `TASK_ID` from the developer
completion summary into the supervisor finalization path instead of relying on
branch-name lookup alone.

### Task 3 — Post-merge branch safety

Teach the reviewed Codex supervisor to remember the exact `main` commit created
by supervisor merge and reject any later turn that leaves dirty edits or new
commits on `main`.

### Task 4 — Regression coverage

Add focused tests for:

- branch-to-task reconciliation
- task-done plus sprint-complete propagation
- unresolved branch lookup returning no result
- reviewed Codex refusing to treat post-merge `main` drift as clean success

## Risks

- the new explicit task-id handoff reduces branch-name ambiguity, but older or
  malformed completion summaries still fall back to branch lookup for backward
  compatibility
- this sprint reconciles future supervisor runs; it does not retroactively fix
  stale rows from older sessions
- reviewed Claude still lacks dedicated regression tests in this repo, so its
  wiring is covered by shared helper behavior rather than script-specific tests

## Validation

- `./venv/bin/python -m pytest tests/test_supervisor_state.py -q`
- `./venv/bin/python -m pytest tests/test_reviewed_codex.py -q`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
