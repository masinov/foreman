# refactor/facts-based-evidence

## Summary

Sprint 56 slice 8 (review finding E8). Completion evidence states facts tied
to the head commit instead of a weighted score and a verdict. ADR-0018.

## Scope

- `CompletionEvidence`: `score`, `score_breakdown`, `verdict`,
  `verdict_reasons` removed; `tests_status`, `tested_sha`,
  `test_duration_seconds`, `reviewed_sha`, `security_reviewed_sha`,
  `outstanding` added; `from_mapping` loads older stored evidence.
- Builder: tests and review compared with the branch head; `proof_status`
  derived from facts only; scoring functions deleted.
- New `engine.review_recorded` event when a decision role answers; evidence
  rebuilt after each decision step.
- `judge.py`: keyword heuristic deleted; no judge means `unverified`.
- Merge guard messages, `engine.completion_guard` payload, event
  constructors, task API payload, attention digest.
- Reviewer prompts (code, triage, frontier) describe the evidence as facts.
- Task drawer: rows for tests, code review, security review and criteria,
  each with its commit; a "not checked" criterion carries no pass/fail mark.

## Files changed

`foreman/models.py`, `orchestrator.py`, `judge.py`, `builtins.py`,
`events.py`, `store.py`, `dashboard_service.py`, `digest.py`, `settings.py`;
`roles/code_reviewer.toml`, `triage_reviewer.toml`, `frontier_reviewer.toml`;
`frontend/src/components.jsx`, `format.js`, `styles.css`, rebuilt bundle;
tests; ADR-0018, README, changelog, sprint, backlog.

## Migrations

None. Stored evidence JSON with the old keys still loads.

## Risks

- A workflow in which a reviewer commits to the task branch is now blocked at
  merge (approval and tests are about an older commit).
- External consumers of `verdict` or `score` in events or the task payload
  will not find them.

## Tests

Full Python suite, `ruff check`, frontend `vitest` and build.

## Acceptance criteria satisfied

Slice 8 as written in `docs/sprints/current.md`.

## Follow-ups

Judge on by default; acceptance tests in a protected path (backlog).
