# Current Sprint

- Sprint: `sprint-46-completion-truth-hardening`
- Status: active
- Branch: `chore/task-false-positive-completion-regression-coverage`
- Started: 2026-04-23

## Goal

Harden Foreman's backend completion evaluation so developer markers and
reviewer approval alone are not enough to count implementation work as done
when evidence is too weak for the task intent.

## Context and rationale

Sprint-45 validated the supervisor finalization seam end-to-end. Sprint-46
attacks the completion truth problem at the evidence-model level: docs-only
and tests-only changes must not be treated as sufficient evidence for
implementation-oriented backend tasks. The evidence model and scoring
mechanism are already designed (feat/completion-truth-evidence-model), so
this sprint adds regression coverage to prove the model is correct before
the backend guard is wired up.

## Constraints

- regression coverage only — do not implement the backend guard yet
- tests must document the expected behavior in the absence of the guard
- do not merge to main — the supervisor handles that after approval

## Affected areas

- `foreman/models.py` — CompletionEvidence.__str__() for prompt-friendly rendering
- `foreman/orchestrator.py` — _build_prompt() injects completion_evidence for code_reviewer
- `roles/code_reviewer.toml` — evidence section before Git Status, explicit weighting instruction
- `tests/test_orchestrator.py` — ReviewerPromptHardeningTests: 7 regression cases
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
- [done] Reviewer prompt hardening with engine-produced evidence (task-reviewer-prompt-hardening-with-engine-produced-evidence)
  - Branch: `feat/task-reviewer-prompt-hardening-with-engine-produced-evidence`
  - Added `CompletionEvidence.__str__()` to render a human-readable evidence block
  - Wired completion evidence into `_build_prompt()` for `code_reviewer` role only when branch_name is set
  - Updated `roles/code_reviewer.toml`: evidence section before Git Status + explicit weighting instruction
  - Added `ReviewerPromptHardeningTests`: 7 regression cases covering all acceptance criteria
- [todo] Backend guard for weak completions (task-backend-guard-for-weak-completions)
- [todo] Completion truth contract docs (task-completion-truth-contract-docs)

## Validation

- `./venv/bin/python -m py_compile tests/test_orchestrator.py`
- `./venv/bin/python scripts/validate_repo_memory.py`
