# PR Summary: chore/task-false-positive-completion-regression-coverage

## Summary

Add regression coverage proving Foreman does not treat docs-only or tests-only changes as sufficient completion for implementation-oriented backend tasks when the completion evidence does not support that outcome.

## Scope

Regression tests for the `CompletionEvidence` dataclass and `build_completion_evidence()` method in `ForemanOrchestrator` (defined on branch `feat/completion-truth-evidence-model` but not yet merged to main). Tests document the expected behavior of the completion evidence model.

## Files changed

- `tests/test_orchestrator.py` — 981-line addition: `CompletionEvidenceTests` class with 14 tests
- `docs/sprints/current.md` — sprint-46 definition with task documentation
- `docs/STATUS.md` — current sprint and active branches updated

## Migrations

- none (regression tests only, no schema or behavior changes)

## Risks

- Tests target the `build_completion_evidence()` API that lives on `feat/completion-truth-evidence-model` and is not yet in `main`. Tests fail on `main` with `AttributeError` until the evidence model branch is merged.
- `CompletionEvidence` dataclass needs to be added to `foreman/models.py` for tests to pass on `main` — this is the next task in sprint-46.

## Tests

14 tests in `CompletionEvidenceTests`:

| Test | Scenario | Expected verdict |
|------|----------|-----------------|
| `test_docs_only_changes_verdict_is_insufficient` | Docs-only changes with APPROVE | `insufficient` |
| `test_tests_only_changes_verdict_is_weak` | Tests-only with APPROVE | `weak` or `insufficient` |
| `test_approval_without_implementation_is_insufficient` | APPROVE with no work | `insufficient` |
| `test_text_claims_implementation_but_no_code_changes_produces_weak_verdict` | Agent claims work but no code changes | `weak` or below |
| `test_passed_tests_alone_without_implementation_is_weak_not_adequate` | Passing tests with placeholder only | `weak` or `insufficient` |
| `test_strong_verdict_requires_code_changes_plus_criteria_plus_passed_tests` | All three signals present | `adequate` or `strong` |
| `test_no_branch_means_no_changed_files_evidence` | No branch set on task | `weak` or `insufficient` |
| `test_failing_test_cancels_test_score_points` | Failing built-in test | `test=0` in breakdown |
| `test_build_completion_evidence_returns_correct_structure` | Structure correctness | pass |
| `test_build_completion_evidence_scores_passed_tests_higher` | Passing tests add 30 pts | `test=30` in breakdown |
| `test_build_completion_evidence_failing_test_receives_zero_test_points` | Failing test | `test=0` in breakdown |
| `test_build_completion_evidence_verdict_weak_when_no_criteria_addressed` | No criteria addressed | `weak` or `insufficient` |
| `test_build_completion_evidence_weak_verdict_despite_criteria_coverage_when_no_code_changes` | Text covers criteria but no code | `weak` |
| `test_build_completion_evidence_no_acceptance_criteria_handled_gracefully` | No criteria text | `insufficient` |

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- [x] Regression coverage proving docs-only changes are insufficient
- [x] Regression coverage proving tests-only changes are insufficient/weak
- [x] Regression coverage proving reviewer approval alone is not sufficient
- [x] Regression coverage proving text claims without code changes produce weak verdict
- [x] Positive case: strong verdict only when all three signals present
- [x] Sprint docs updated to sprint-46

## Follow-ups

- **Next**: `task-backend-guard-for-weak-completions` — wire the verdict into task lifecycle so `insufficient` and `weak` verdicts cause the backend to surface a warning or block
- Wire `CompletionEvidence` dataclass into `foreman/models.py` (depends on `feat/completion-truth-evidence-model` merge)
- Add `build_completion_evidence()` method stub to `ForemanOrchestrator` on `main` so tests pass