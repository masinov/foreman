# PR Summary: feat/judge-and-tiered-review

## Summary

Sprint 51 (review Phases 4 and 5 — token economy). Phase 4 makes the
acceptance-criteria checklist trustworthy by adding an opt-in cheap-model judge
behind the existing keyword heuristic. Phase 5 adds a tiered review path so the
frontier model only adjudicates work a cheap triage reviewer could not
confidently approve, reading a curated diff payload instead of exploring the
repo.

Stacked on the unmerged `feat/executor-overrides-ladder` (Phase 3) →
`feat/meta-agent-persistence` (Phase 2).

## Scope

Phase 4:
- `foreman/judge.py`: `CriteriaJudgment`, `heuristic_checklist`
  (`_criterion_addressed` moved here as the single owner), `truncate_diff`,
  and `judge_criteria` (opt-in Anthropic-compatible `/v1/messages` call)
- `CompletionEvidence.judged_by` (default `"heuristic"`)
- `build_completion_evidence` calls the judge with a real `git diff`
  (`_safe_branch_diff_content`); records and emits `judged_by`

Phase 5:
- `escalate` outcome in `outcomes.py`, `_extract_decision_output`, and the
  reviewer normalizer
- `_VALID_OUTCOMES` for `triage_reviewer` (approve/deny/escalate) and
  `frontier_reviewer` (approve/deny/steer)
- roles `triage_reviewer.toml` (cheap, all tools off) and
  `frontier_reviewer.toml` (frontier, all tools off)
- `{completion_diff}` prompt payload for decision roles
  (`review_diff_max_chars`, default 16000); added to `code_reviewer`,
  `security_reviewer`, and the two new roles
- `workflows/development_tiered.toml`

## Files changed

- `foreman/judge.py` (new), `foreman/models.py`, `foreman/orchestrator.py`,
  `foreman/outcomes.py`, `foreman/workflows.py`
- `roles/triage_reviewer.toml` (new), `roles/frontier_reviewer.toml` (new),
  `roles/code_reviewer.toml`, `roles/security_reviewer.toml`
- `workflows/development_tiered.toml` (new)
- `tests/test_judge.py` (new), `tests/test_orchestrator.py`,
  `tests/test_workflows.py`, `tests/test_roles.py`, `tests/test_cli.py`
- `docs/STATUS.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`

## Migrations

- none (additive dataclass default `judged_by` keeps old serialized evidence
  loadable)

## Risks

- The judge is a network call; it is strictly opt-in and every failure path
  (unset settings, HTTP error, timeout, malformed/short/long output) falls back
  to the heuristic, so evidence building never crashes the workflow.
- The frontier reviewer's `STEER: need repository context` currently routes
  back to develop; a tool-enabled agentic re-review escape hatch is out of
  scope and noted in the backlog.

## Tests

- `tests/test_judge.py` — heuristic fallback, happy path, fenced JSON,
  malformed/short output → heuristic, timeout/HTTP error → heuristic,
  truncation marker (10 tests)
- `tests/test_orchestrator.py` — judge-configured evidence sets
  `judged_by=<model>`; heuristic default; tiered triage `ESCALATE` routes to
  frontier review with the reason carried; triage `APPROVE` skips frontier;
  `completion_diff` only for decision roles with the truncation marker;
  `_extract_decision_output` recognizes `ESCALATE`
- `tests/test_workflows.py` — `development_tiered` loads and resolves the
  escalate edge; a broken triage `steer` transition is rejected
- `tests/test_roles.py`, `tests/test_cli.py` — shipped role/workflow listings
- `./venv/bin/python -m unittest discover -s tests` — full suite (see commit)
- `./venv/bin/python scripts/validate_repo_memory.py`; `git diff --check`

## Acceptance criteria satisfied

Phase 4:
- judge unit tests with a fake httpx transport cover happy path, fenced JSON,
  malformed → fallback, timeout → fallback, unset settings → heuristic.
- judge-configured evidence shows `judged_by=<model>` in the event; unset is
  byte-identical to the prior heuristic (existing evidence tests still pass).

Phase 5:
- the loader accepts `development_tiered` and rejects a deliberately broken
  copy.
- triage `ESCALATE` routes to the frontier review step with the reason in
  events; triage `APPROVE` skips the frontier entirely.
- developer prompt contains no diff payload; the triage prompt contains the
  capped diff with the truncation marker when oversized.

## Follow-ups

- Sprint 52 (Phases 6–7): manager supervision turns for
  `engine.attention_needed`, SSE/watch polling via SQLite `data_version`,
  persisted retry counts, and the multi-model/tiered documentation pass.
- Optional: tool-enabled re-review routing for frontier `STEER` (backlog).
