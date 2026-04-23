# Current Sprint

- Sprint: `sprint-46-completion-truth-hardening`
- Status: active
- Branch: `fix/merge-conflict-recovery-review-loop`
- Started: 2026-04-23

## Goal

Harden Foreman's backend completion evaluation so developer markers and
reviewer approval alone are not enough to count implementation work as done
when evidence is too weak for the task intent.

## Context and rationale

Sprint-45 validated the supervisor finalization seam end to end. Sprint-46
hardens completion truth in two stages: first the evidence model and
regression coverage, then the backend guard that uses branch diff evidence
to stop implementation tasks from flowing to `done` when they only changed
docs/tests or never produced material branch changes. While running those
tasks live, Foreman exposed follow-on runtime defects around native-step
recovery, dirty finalization, malformed output contracts, and stale
task-branch reuse. The current branch fixes the stale-branch merge-conflict
loop: merge conflicts are now distinguished from generic merge failures,
conflict-resolution passes get explicit carried guidance, and existing task
branches are refreshed against current `main` when that refresh is clean
before the developer tries again.

## Constraints

- backend only — no dashboard or legacy supervisor script work
- guard must operate before terminal completion so valid tasks do not get
  blocked after a successful merge
- keep the shipped workflow shape intact: `develop -> review -> test -> merge -> done`
- do not merge to main — the supervisor handles that after approval

## Affected areas

- `foreman/builtins.py` — merge conflict outcome and conflict-specific carry output
- `foreman/git.py` — merge-conflict detection + stale task-branch refresh helper
- `foreman/orchestrator.py` — conflict-recovery branch preparation and re-review loop
- `workflows/development.toml` — explicit `completion:conflict` transition
- `tests/test_orchestrator.py` — conflict-loop and stale-branch refresh regressions
- `docs/sprints/current.md` — this sprint definition
- `docs/STATUS.md` — task and sprint status

## Tasks

- [done] Completion evidence model in orchestrator (task-completion-evidence-model-in-orchestrator)
  - Branch: `feat/completion-truth-evidence-model`
  - Added `CompletionEvidence` dataclass to `foreman/models.py`
  - Added `build_completion_evidence()` to `ForemanOrchestrator`
  - Scoring: criteria (40 pts), files (20 pts), diff context (10 pts), tests (30 pts)
  - Verdicts: strong, adequate, weak, insufficient
  - `_criterion_addressed()` — keyword coverage ratio against output + changed files
  - Persisted via `completion_evidence_json` column in tasks table
  - Wired into `finalize_supervisor_merge()` with `engine.completion_evidence` event
- [done] False-positive completion regression coverage (task-false-positive-completion-regression-coverage)
  - Branch: `chore/task-false-positive-completion-regression-coverage` (this branch)
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
- [todo] Completion truth contract docs (task-completion-truth-contract-docs)
- [todo] Reviewer prompt hardening with engine-produced evidence (task-reviewer-prompt-hardening-with-engine-produced-evidence)

## Validation

- `./venv/bin/python -m pytest tests/test_orchestrator.py -q`
- `./venv/bin/python -m pytest tests/test_store.py tests/test_executor.py tests/test_roles.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`
