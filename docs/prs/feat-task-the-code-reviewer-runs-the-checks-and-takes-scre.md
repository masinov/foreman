# PR Summary: feat/task-the-code-reviewer-runs-the-checks-and-takes-scre

## Summary

- Roles gain `run_scope` (`none`, `sandbox`, `branch`; unset is `branch`, today's behaviour).
- A `sandbox` step runs in a detached git worktree at the commit under review, prepared like a task worktree, removed when the step ends however it ends.
- Foreman checks the task's branch after the step, restores it if it moved, and fails the step with the reason. Pushes are pointed nowhere.
- The shipped `code_reviewer` runs in a sandbox with Bash; its prompt asks for checks, and for `frontend/` changes, screenshots at 1440 and 390 px.

## Scope

- Role loader, `WorktreeManager.sandbox`, `AgentStepRunner`, the `code_reviewer` role, docs. No write-scope or inputs work (ADR-0041 section 5's other bullets).

## Files changed

- `foreman/definitions/roles.py`, `foreman/repo/worktrees.py`, `foreman/engine/agent_step.py`
- `foreman/data/roles/code_reviewer.toml`
- `tests/test_sandbox.py` (new); `tests/test_agent_sandbox.py`, `test_engine_agent_step.py`, `test_worktrees.py`, `test_project_definitions.py` updated for the reviewer's new tools and sandbox directory
- `docs/ARCHITECTURE.md`, `docs/adr/ADR-0023-...md`, `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- Only the task's branch is guarded; branches or tags the agent creates in the sandbox stay in the shared repository (other refs move legitimately while a review runs).
- The sandbox runs `worktree_setup_command` on every review step, which can be slow for a project with a heavy setup.
- The process still runs as the engine's user with network access (ADR-0023 "Not covered").
- The Playwright screenshot instructions were not exercised by a real reviewer run here.

## Tests

- `tests/test_sandbox.py`: loader accepts/refuses scopes; sandbox removed on success, failure, kill and setup failure; commit in the sandbox leaves the branch alone; moved or deleted branch restored and step failed; push blocked.
- Full suite: `./venv/bin/python -m pytest tests -n auto -q`.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Loader accepts `none`, `sandbox`, `branch` and refuses others; a role without it is unchanged.
- Worktree removed after success, failure and kill.
- A step that moves a ref leaves the branch head unchanged and fails with the reason.
- Shipped `code_reviewer` is sandboxed with Bash and asks for checks and 1440/390 px screenshots.
- `docs/ARCHITECTURE.md` describes the sandbox.

## Follow-ups

- Write scope and inputs (ADR-0041 section 5); a container per task (ADR-0023 later steps).
