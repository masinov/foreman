# ADR-0010: Tiered Review, LLM-Judged Evidence, and the Escalation Ladder

- Status: accepted
- Date: 2026-06-13

## Context

The review roadmap's token-economy phases ask the engine to spend frontier-model
budget only where it earns its cost, while keeping completion evidence
trustworthy enough for both the manager and a senior reviewer to lean on.

Three decisions reached implementation in sprints 50–51 and are now active
constraints:

1. how per-task model selection escalates on repeated failure,
2. how acceptance-criteria evidence is judged, and
3. how review tiers are arranged so the frontier model reviews only escalated
   work.

## Decision

### Model selection escalates on workflow step visits

A role may define `[agent] model_ladder = [...]`. `resolve_step_model` picks the
rung by step-visit count (`ladder_start + visit_count - 1`, clamped), so a step
that keeps failing automatically escalates to a more capable model. Per-task
`executor_overrides` can pin a step's model or shift the ladder start; an
override that itself appears in the ladder resumes escalation from its index.
Precedence is deterministic: override → ladder → role `model` → project
`default_model` → harness default. Each agent step emits a
`workflow.model_selected` event recording the chosen model and the rule that
chose it.

Different ladder rungs share one role's `[agent.env]`. Rungs that need
different endpoints must be modeled as different roles per workflow step;
per-model environment maps are intentionally not supported (see ADR-0009).

### The criteria judge is a direct HTTP call, not a harness session

Acceptance-criteria judging lives in `foreman/judge.py`. The zero-config keyword
heuristic is the default and the single owner of the keyword logic. When
`judge_base_url` and `judge_model` are set, `judge_criteria` issues one direct
HTTP call to an Anthropic-compatible `/v1/messages` endpoint — it needs no tools
and must be cheap and fast, so a harness session would be the wrong shape. Any
failure (unset settings, HTTP error, timeout, unparseable or wrong-length
output) falls back to the heuristic; evidence building must never crash the
workflow. The deciding judge is recorded as `CompletionEvidence.judged_by` and
emitted in `engine.completion_evidence`.

### Review is tiered; the frontier reviewer reads a curated payload

`development_tiered` inserts a cheap `triage_reviewer` between develop and the
frontier `review`. Triage returns `APPROVE` / `DENY` / `ESCALATE`; only
`ESCALATE` routes to the tool-less `frontier_reviewer`, which adjudicates from a
curated `{completion_diff}` payload rather than exploring the repo. Decision
roles receive the capped diff payload (`review_diff_max_chars`); other roles do
not. The agentic `code_reviewer` is retained as the escape hatch and is not
de-tooled.

## Consequences

- Frontier budget is spent only on work a cheap reviewer could not confidently
  adjudicate.
- `proof_status` can be backed by a real model judgment while remaining
  byte-identical to the prior heuristic when the judge is unconfigured.
- A tool-enabled "re-review" routing when the frontier reviewer answers
  `STEER: need repository context` is out of scope; today that carry-output edge
  returns to develop. Recorded as a backlog follow-up.
