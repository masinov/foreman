# Current Sprint

- Sprint: `sprint-46-completion-truth-hardening`
- Status: active
- Branch: `docs/task-completion-truth-contract-docs`
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

## Constraints

- do not merge to main — the supervisor handles that after approval
- backend only
- do not manually edit `.foreman.db`
- do not target `scripts/reviewed_claude.py` or `scripts/reviewed_codex.py`
  as product work
- preserve the shipped workflow shape:
  `develop -> review -> test -> merge -> done`
- if a developer resolves a merge conflict, the task must pass through
  `review` again before merge

## Affected areas

- `tests/test_orchestrator.py` — CompletionEvidenceTests class with 14 tests
- `foreman/orchestrator.py` — completion guard wiring
- `foreman/models.py` — CompletionEvidence dataclass
- `foreman/git.py`
- `foreman/builtins.py`
- `foreman/store.py`
- `foreman/migrations.py`
- `docs/sprints/current.md` — this sprint definition
- `docs/STATUS.md` — task and sprint status
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
  - Added 14 tests in `CompletionEvidenceTests` covering:
    - `test_docs_only_changes_verdict_is_insufficient` — docs-only → verdict=insufficient
    - `test_tests_only_changes_verdict_is_weak` — tests-only → verdict in (weak, insufficient)
    - `test_approval_without_implementation_is_insufficient` — reviewer APPROVE alone → verdict=insufficient
    - `test_text_claims_implementation_but_no_code_changes_produces_weak_verdict` — text coverage without code changes → verdict=weak
    - `test_passed_tests_alone_without_implementation_is_weak_not_adequate` — passing tests without implementation → verdict ≤ weak
    - `test_strong_verdict_requires_code_changes_plus_criteria_plus_passed_tests` — positive case: all three signals → verdict adequate/strong
    - `test_no_branch_means_no_changed_files_evidence` — no branch → no diff, verdict driven by output alone
    - `test_failing_test_cancels_test_score_points` — failing test → test=0 in score breakdown
    - 6 baseline tests: structure, scoring, verdict, coverage, no-criteria edge case
- [done] Backend guard for weak completions (task-backend-guard-for-weak-completions)
  - Branch: `feat/task-backend-guard-for-weak-completions`
  - Wires `weak`/`insufficient` verdict into task lifecycle at merge time
  - Blocks merge commit when verdict is below `adequate`
- [done] Completion truth contract docs (task-completion-truth-contract-docs)
  - Branch: `docs/task-completion-truth-contract-docs`
  - Created `docs/adr/ADR-0008-completion-truth-contract.md`
  - Captures: evidence dimensions, 4-component scoring (100 pts max), verdict
    thresholds (strong/adequate/weak/insufficient), insufficient-evidence
    scenarios, wiring into `finalize_supervisor_merge()` and persistence via
    `completion_evidence_json`
- [todo] Reviewer prompt hardening with engine-produced evidence (task-reviewer-prompt-hardening-with-engine-produced-evidence)
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
