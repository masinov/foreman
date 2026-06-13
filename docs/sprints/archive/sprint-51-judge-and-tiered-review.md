# Sprint 51 — Review Phases 4 & 5 Token Economy

- **Branch:** `feat/judge-and-tiered-review` (stacked on
  `feat/executor-overrides-ladder`)
- **Merged:** 2026-06-13 (fast-forward to `main` at `b53f930`)
- **Status:** done

## Goal

Add opt-in LLM-judged criteria evidence, diff payloads for reviewers, cheap
triage review with an `escalate` outcome, and the `development_tiered`
workflow.

## Tasks completed

| # | Task | Deliverable |
|---|------|-------------|
| 1 | LLM judge | `foreman/judge.py` — keyword heuristic (`heuristic_checklist`, `_criterion_addressed`) is the single owner; `judge_criteria` adds an opt-in cheap-model judge via a direct Anthropic-compatible `/v1/messages` call (settings `judge_base_url`, `judge_model`, `judge_api_key_env`, `judge_max_diff_chars`); head/tail diff truncation; any HTTP/timeout/parse error falls back to the heuristic so evidence never crashes the workflow |
| 2 | Evidence wiring | `build_completion_evidence` calls `judge_criteria` (`_safe_branch_diff_content` for the full `git diff`); records `CompletionEvidence.judged_by` (default `heuristic`, keeps old evidence loadable) and emits it in `engine.completion_evidence`. Heuristic path byte-identical |
| 3 | Escalate outcome | `ESCALATE` in `outcomes.py`, `_extract_decision_output`, `_VALID_OUTCOMES` for `triage_reviewer`/`frontier_reviewer`; reviewer normalization extended |
| 4 | Tiered roles | `triage_reviewer` (cheap, all tools off) and `frontier_reviewer` (frontier, all tools off); both review a curated payload only |
| 5 | Diff payload | `_build_prompt` adds `{completion_diff}` (capped `default_branch...branch` diff, `review_diff_max_chars` default 16000), populated only for `extract_decision` roles; added to `code_reviewer`, `security_reviewer`, and the two new roles |
| 6 | Tiered workflow | `workflows/development_tiered.toml` — develop → triage; triage approve→test, deny→develop, escalate→frontier review; review approve→test, deny/steer→develop; test/merge/done identical to `development` (including `completion:conflict`) |

## Files changed

`foreman/judge.py` (new), `foreman/models.py`, `foreman/orchestrator.py`,
`foreman/outcomes.py`, `foreman/workflows.py`, `roles/triage_reviewer.toml`
(new), `roles/frontier_reviewer.toml` (new), `roles/code_reviewer.toml`,
`roles/security_reviewer.toml`, `workflows/development_tiered.toml` (new),
`tests/test_judge.py` (new, 10), `tests/test_orchestrator.py`,
`tests/test_workflows.py`, `tests/test_roles.py`.

## Test results

- `tests.test_judge` (10), workflow/role listing, `CompletionEvidenceTests`
- Full suite passed
- `scripts/validate_repo_memory.py`

## Follow-ups

- Deferred (backlog): a tool-enabled agentic re-review when the frontier
  reviewer answers `STEER: need repository context` (today routes back to
  develop).
- Stacked-on by Sprint 52 (supervision + transport).
