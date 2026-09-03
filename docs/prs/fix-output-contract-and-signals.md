# PR Summary: fix/output-contract-and-signals

## Summary

Sprint 53, slice 3. The agent's final message is now the contract. Before
this slice the completion marker counted anywhere in the transcript, the
last decision-shaped line won for reviewers, signals were applied twice on
the Claude path, any role could create tasks, and the engine recognized
reviewers by four hardcoded role ids, which also meant a tiered-review
approval never satisfied the merge guard.

## Scope

- **Final message only.** `_execute_native_runner_step` tracks the final
  assistant message (Claude `result`, Codex `final_answer`, else the last
  message) and applies the role contract to it. A marker echoed in an early
  plan no longer completes a task; a reviewer's restated options footer no
  longer flips the verdict. The returned detail is the cleaned final message,
  falling back to the transcript only when the final message was just the
  marker.
- **Decision grammar.** `_extract_decision_output` accepts the bare verdict,
  `VERDICT: reason`, markdown emphasis, list markers, and a `Decision:` /
  `Verdict:` prefix; ignores `<placeholder>` option lines; treats more than
  one distinct verdict as an error ("Ambiguous decision"); and rejects a
  verdict the role does not declare. Both errors trigger the existing
  one-shot output-contract retry, whose correction now lists the role's own
  outcomes.
- **Role-declared contracts.** Roles declare `[completion] outcomes`
  (defaulting to approve/deny/steer for decision roles and done/blocked/error
  otherwise), `[completion] review_kind` (`code` or `security`), and
  `[signals] allowed`. The orchestrator normalizes by
  `completion.output.extract_decision` instead of role ids, workflow
  validation reads `role_outcomes` from the loaded roles instead of a
  hardcoded table, and the evidence builder classifies reviewer runs by
  `review_kind`. Every reviewer now receives the `{completion_evidence}`
  payload, not only `code_reviewer`.
- **Signals.** `extract_signal_events` ignores signals inside code fences and
  quoted lines and accepts pretty-printed JSON spanning lines (brace-balanced,
  up to 40 lines). The Claude runner no longer re-emits signals from the
  `result` text when an assistant block already carried them. The
  orchestrator deduplicates identical signals within a step and records a
  `signal.rejected` event, without applying, when a role emits a signal it
  is not allowed to (reviewers may only report progress and blockers).
- **Built-ins.** `BuiltinExecutor.execute` accepts an `evidence_builder`; the
  orchestrator passes its own so the merge guard evaluates evidence with the
  same role definitions that ran the workflow.

## Files changed

- `foreman/roles.py`, `foreman/workflows.py`, `foreman/orchestrator.py`,
  `foreman/builtins.py`, `foreman/runner/signals.py`,
  `foreman/runner/claude_code.py`, `foreman/cli.py`,
  `foreman/dashboard_service.py`
- `roles/code_reviewer.toml`, `roles/security_reviewer.toml`,
  `roles/triage_reviewer.toml`, `roles/frontier_reviewer.toml`,
  `roles/architect.toml`
- `tests/test_output_contract.py` (new, 18 tests), `tests/test_workflows.py`
- `docs/sprints/current.md`, `docs/STATUS.md`, `docs/MANUAL.md`,
  `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `CHANGELOG.md`

## Migrations

- None.

## Risks

- **Behavior change:** a developer whose final message lacks the marker now
  gets the corrective retry even if an earlier message contained it. That is
  the intended tightening.
- **Behavior change:** the developer summary carried to reviewers is the final
  message rather than the whole transcript concatenated. Reviewer prompts
  were written for a summary; the diff payload and evidence carry the rest.
- **Behavior change:** the tiered workflow now passes the merge guard on a
  frontier or triage approval. Previously it only passed with
  `completion_guard_enabled = false`.
- Custom roles that emit `task_created` or `task_started` must declare
  `[signals] allowed`; the default remains all four signals.

## Tests

- `./venv/bin/python -m unittest discover -s tests` — 638 passing (was 620;
  +18 in `tests/test_output_contract.py`).
- `scripts/validate_repo_memory.py` clean; `git diff --check` clean.

## Acceptance criteria satisfied

- a marker echoed early does not complete a task; a marker in the final
  message does,
- two distinct verdicts in one review produce an error and a retry, not a
  guess,
- a signal quoted in a fence or repeated by the result stream is applied once,
- a reviewer cannot create tasks; the attempt is recorded as
  `signal.rejected`,
- a custom decision role declared in TOML flows through review, test, and
  merge without any engine change,
- a tiered review approval satisfies the completion guard.

## Follow-ups

- Sprint 53 slices 4–6.
- Phase 1: agent-created tasks enter through intake with a policy-chosen
  status instead of landing as `todo` in the active sprint.
