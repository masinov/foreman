# Current Sprint

- Sprint: `sprint-46-completion-truth-hardening`
- Status: active
- Branch: `main`
- Started: 2026-04-23
- Next queued sprint: `sprint-47-active-run-lease-and-heartbeat-recovery`

## Goal

Harden Foreman's backend completion evaluation so developer completion markers
and reviewer approval alone are not enough to count implementation work as
done when the evidence is too weak for the task intent.

## Context and rationale

Sprint 45 validated the supervisor finalization seam end to end in the live
repository. Sprint 46 focuses on completion truth: structured evidence,
backend guards against weak completions, and reviewer context that reflects
engine-produced evidence instead of raw agent claims alone.

The live sprint-46 runs also exposed follow-on runtime defects:

- native-step ownership and stale-run recovery
- dirty task finalization from uncommitted worktree state
- malformed developer and reviewer output contracts
- stale task-branch reuse causing deterministic merge-conflict loops

Those runtime fixes are now merged into local `main`. The remaining sprint-46
work should be rerun on that corrected baseline.

## Constraints

- backend only
- do not manually edit `.foreman.db`
- do not target `scripts/reviewed_claude.py` or `scripts/reviewed_codex.py`
  as product work
- preserve the shipped workflow shape:
  `develop -> review -> test -> merge -> done`
- if a developer resolves a merge conflict, the task must pass through
  `review` again before merge

## Affected areas

- `foreman/orchestrator.py`
- `foreman/git.py`
- `foreman/builtins.py`
- `foreman/store.py`
- `foreman/migrations.py`
- `roles/developer.toml`
- `roles/code_reviewer.toml`
- `workflows/development.toml`
- orchestrator, migration, role, and executor regression tests
- repo-memory docs for the completion-truth contract

## Tasks

- [done] Completion evidence model in orchestrator (task-completion-evidence-model-in-orchestrator)
  - Branch: `feat/completion-truth-evidence-model`
  - Added `CompletionEvidence` to `foreman/models.py`
  - Added `build_completion_evidence()` to `ForemanOrchestrator`
  - Persisted evidence via `completion_evidence_json` in SQLite
  - Emitted `engine.completion_evidence` during supervisor merge finalization

- [done] False-positive completion regression coverage (task-false-positive-completion-regression-coverage)
  - Branch: `chore/task-false-positive-completion-regression-coverage`
  - Added coverage proving docs-only, tests-only, or output-only completions
    are not sufficient evidence for implementation tasks

- [done] Backend guard for weak completions (task-backend-guard-for-weak-completions)
  - Branch: `feat/task-backend-guard-for-weak-completions`
  - Added completion guard enforcement before terminal completion
  - Hardened `_builtin:merge` and `_builtin:mark_done` against dirty or
    non-committed branch finalization

- [blocked] Completion truth contract docs (task-completion-truth-contract-docs)
  - Branch: `docs/task-completion-truth-contract-docs`
  - Previously stalled in a merge-conflict loop due to stale branch reuse
  - Should be rerun on the corrected conflict-recovery path

- [blocked] Reviewer prompt hardening with engine-produced evidence (task-reviewer-prompt-hardening-with-engine-produced-evidence)
  - Branch: `feat/task-reviewer-prompt-hardening-with-engine-produced-evidence`
  - Previously stalled after malformed output-contract and stale-branch issues
  - Should be rerun on the corrected runtime path

- [blocked] Reviewer prompt hardening follow-up: cache completion evidence on task record (task-4221cd659154)
  - Branch: `chore/task-4221cd659154`
  - Left blocked by malformed reviewer output during the live run
  - Should be rerun on the corrected runtime path

## Validation

- `./venv/bin/python -m pytest tests/test_orchestrator.py -q`
- `./venv/bin/python -m pytest tests/test_store.py tests/test_executor.py tests/test_roles.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Next Queued Sprint

- Sprint: `sprint-47-active-run-lease-and-heartbeat-recovery`
- Status: planned
- Queue position: next planned sprint, ahead of the older deferred `sprint-008`
