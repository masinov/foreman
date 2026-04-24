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
  - Added completion guard to `_builtin:mark_done` in `foreman/builtins.py`
  - Guard mirrors the existing `_builtin:merge` guard: builds completion evidence (git diff,
    criteria coverage, test results) and blocks feature/fix/refactor tasks when evidence is weak
    (no material code changes, or docs/tests-only changes)
  - Post-merge invocation handled via `git merge-base --is-ancestor feat/t main`: when the task
    branch has been absorbed into the default branch, the diff is naturally empty but the guard
    already ran at merge time, so mark_done proceeds without re-evaluating
  - Guard respects `completion_guard_enabled` project setting (default True) and skips for
    non-implementation task types (docs/spike/chore)
  - 7 regression tests in `MarkDoneCompletionGuardTests`: strong/adequate pass, insufficient/weak
    block, event emission, guard-disable setting, non-implementation task type bypass
- [done] Reviewer prompt hardening with engine-produced evidence follow-up: cache completion evidence on task record (task-4221cd659154)
  - Branch: `chore/task-4221cd659154` (this branch)
  - `CompletionEvidence` is built once at first reviewer prompt render via `build_completion_evidence()` in `_build_prompt`
  - Persisted to the task record via `store.save_task()` after first build
  - Subsequent reviewer prompts reuse `task.completion_evidence` without recomputing
  - Evidence fields injected into reviewer prompt context: verdict, reasons, score, score_breakdown, criteria counts, changed files, diff stat, builtin test result
  - `Task.completion_evidence` typed as `CompletionEvidence | None` in models.py
  - Store deserializes `CompletionEvidence` from JSON in `_row_to_task`
- [todo] Completion truth contract docs (task-completion-truth-contract-docs)
- [todo] Reviewer prompt hardening with engine-produced evidence (task-reviewer-prompt-hardening-with-engine-produced-evidence)

## Validation

- `./venv/bin/python -m pytest tests/test_orchestrator.py -q`
- `./venv/bin/python -m pytest tests/test_store.py tests/test_executor.py tests/test_roles.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Next Queued Sprint

- Sprint: `sprint-47-active-run-lease-and-heartbeat-recovery`
- Status: planned
- Queue position: next planned sprint, ahead of the older deferred `sprint-008`
