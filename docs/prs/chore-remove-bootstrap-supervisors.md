# PR Summary: chore/remove-bootstrap-supervisors

## Summary

Sprint 53, slice 6, closing Phase 0. Removes the bootstrap supervisor scripts
that drove this repository before the engine could, along with the legacy
supervisor-merge path they called into, drops the unused `anthropic`
dependency, and stops rendering the autonomous-mode signal contract into
every directed task's context. Closes sprint 53 and archives it.

## Scope

- **Removed:** `scripts/reviewed_claude.py`, `scripts/reviewed_codex.py`,
  `tests/test_reviewed_claude.py`, `tests/test_reviewed_codex.py`,
  `foreman/supervisor_state.py`, `tests/test_supervisor_state.py`, the
  orchestrator's legacy `finalize_supervisor_merge` method, its
  `SupervisorMergeResult` dataclass, and its three orchestrator tests.
  `_builtin:mark_done` plus `_builtin:merge` is the only completion path.
- **Dependency:** `anthropic` dropped from `pyproject.toml`; nothing imported
  it (the criteria judge calls the Messages endpoint with `httpx`).
- **Context projection:** `.foreman/context.md` includes the "Autonomous
  Signal Contract" section only when the project's `task_selection_mode` is
  `autonomous`; directed tasks already carry their title, branch, and
  criteria.
- **Validator:** `scripts/repo_validation.py` no longer requires the removed
  scripts.
- **Docs:** `AGENTS.md` (validation baseline now includes the unit suite;
  "Wrapper Expectations" replaced by "Autonomous Entry Point"), `README.md`,
  `docs/TESTING.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`, an amendment
  on `ADR-0008`, the sprint archive, and a checkpoint.

## Files changed

- `foreman/orchestrator.py`, `foreman/context.py`, `pyproject.toml`,
  `scripts/repo_validation.py`
- deleted: `scripts/reviewed_claude.py`, `scripts/reviewed_codex.py`,
  `foreman/supervisor_state.py`, `tests/test_reviewed_claude.py`,
  `tests/test_reviewed_codex.py`, `tests/test_supervisor_state.py`
- `tests/test_orchestrator.py`
- `AGENTS.md`, `README.md`, `CHANGELOG.md`, `docs/TESTING.md`,
  `docs/ARCHITECTURE.md`, `docs/STATUS.md`,
  `docs/adr/ADR-0008-completion-truth-contract.md`,
  `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `docs/sprints/archive/sprint-53-phase0-unattended-safety.md`,
  `docs/checkpoints/2026-09-04-sprint-53-phase0-unattended-safety.md`

## Migrations

- None.

## Risks

- Anyone still invoking the removed scripts must switch to `foreman run`.
  They were marked deprecated before this sprint and had no product caller.
- The `anthropic` package stays installed in existing virtual environments
  until reinstalled; nothing depends on it either way.

## Tests

- `./venv/bin/python -m unittest discover -s tests` — 605 passing
  (was 661; 56 tests removed with the scripts, the adapter, and the legacy
  path).
- `scripts/validate_repo_memory.py` clean; `git diff --check` clean.

## Acceptance criteria satisfied

- no bootstrap supervisor code or tests remain in the repository,
- the only completion path is the workflow's built-in merge and mark-done
  steps,
- the package declares only dependencies it imports,
- directed tasks no longer receive the autonomous contract text.

## Follow-ups

- Phase 1 (`docs/sprints/backlog.md`): resident worker, intake endpoint,
  policy matrix, planner step, worktree isolation, pull-request integration,
  facts-based verification, identity and notifications, chat hardening.
