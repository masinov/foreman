# PR Summary: feat/task-reviewer-prompt-hardening-with-engine-produced-evidence

## Summary

Update the real Foreman review path so reviewer prompts receive explicit engine-produced completion evidence rather than relying only on free-form developer summaries and raw git context.

## Scope

- `CompletionEvidence.__str__()` in `foreman/models.py` — renders a human-readable evidence block (score, verdict, criteria coverage, diff stat, test result) for direct injection into agent prompts.
- `ForemanOrchestrator._build_prompt()` in `foreman/orchestrator.py` — calls `build_completion_evidence()` and injects the result as `{completion_evidence}` in the `code_reviewer` role context.
- `roles/code_reviewer.toml` — added evidence section before Git Status with explicit instruction to weight weak verdicts heavily before issuing APPROVE.
- `tests/test_orchestrator.py` — `ReviewerPromptHardeningTests`: 7 regression cases.

## Files changed

- `foreman/models.py` — `CompletionEvidence.__str__()` (+14 lines)
- `foreman/orchestrator.py` — `_build_prompt()` injects `completion_evidence` for `code_reviewer` (+5 lines)
- `roles/code_reviewer.toml` — evidence section before Git Status + weighting instruction (+11 lines)
- `tests/test_orchestrator.py` — `ReviewerPromptHardeningTests`: 7 tests (+426 lines)
- `docs/sprints/current.md` — task marked done
- `docs/STATUS.md` — active branch updated

## Migrations

- none (no schema changes)

## Risks

- `completion_evidence` section header always renders in reviewer prompts (even when empty), because the TOML template unconditionally includes it. A reviewer seeing an empty evidence block should interpret it as a missing signal.
- Evidence is built fresh on every reviewer prompt render; for very large diffs or many prior runs this has linear cost. Future work could cache the evidence on the task record.

## Tests

7 tests in `ReviewerPromptHardeningTests`:

| Test | Scenario | Expected |
|------|----------|----------|
| `test_completion_evidence_appears_in_reviewer_prompt_when_branch_set` | Branch exists | Evidence section present |
| `test_completion_evidence_content_absent_when_no_branch` | No branch set | No evidence score/criteria content |
| `test_completion_evidence_absent_from_developer_prompt` | Developer role | No evidence section |
| `test_evidence_section_contains_verdict_and_score` | Branch + work done | Evidence score and verdict present |
| `test_evidence_section_before_git_status_in_reviewer_prompt` | Template order | Evidence before Git Status |
| `test_no_branch_no_evidence_content_in_reviewer_prompt` | No branch, 3 criteria | No evidence content |
| `test_evidence_section_includes_criteria_coverage_counts` | 3 criteria | Criteria coverage visible |

Full suite: 400 tests pass (including all 14 CompletionEvidenceTests and all 7 ReviewerPromptHardeningTests).

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- [x] Reviewer prompts receive explicit engine-produced completion evidence
- [x] Evidence is gated on `role.id == "code_reviewer"` and `task.branch_name` being set
- [x] Evidence absent from developer and other role prompts
- [x] Evidence section positioned before Git Status in template
- [x] Evidence includes score, verdict, criteria coverage, diff stats, test result
- [x] Regression tests cover all key scenarios
- [x] Sprint docs updated

## Follow-ups

- **Next**: `task-backend-guard-for-weak-completions` — wire the evidence verdict into the orchestrator so tasks with `verdict=insufficient` are automatically blocked rather than advancing to merge. This task is blocked waiting for this branch's completion.
- **Docs**: `task-completion-truth-contract-docs` — document the completion truth contract, also blocked waiting for this task.
