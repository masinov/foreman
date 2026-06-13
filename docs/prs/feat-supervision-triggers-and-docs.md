# PR Summary: feat/supervision-and-transport → feat/supervision-triggers-and-docs

## Summary

Two things: (1) close the single functional gap found by the independent backend
audit of `docs/specs/review.md` — the supervision attention-trigger taxonomy was
only partially wired; (2) ship `docs/MANUAL.md`, a complete operator's usage
manual, and point the README at it.

## Scope

### Gap fix (review Phase 6 completeness)

`foreman/digest.py` defines four supervision triggers (`task_blocked`,
`evidence_failed`, `loop_limit`, `sprint_resolved`) but the orchestrator only
ever emitted `task_blocked` and `loop_limit`. Now:

- **`evidence_failed`** — a builtin completion/merge guard block
  (`_merge`/`_mark_done`) sets the task blocked itself and never routed through
  `_create_system_run`, so no attention turn fired. The builtin-step path now
  raises one `engine.attention_needed` on a blocked builtin outcome, tagged
  `evidence_failed` when the task's rebuilt `proof_status == "failed"` (via the
  new `_attention_trigger_for_block`), else `task_blocked`.
- **`sprint_resolved`** — `_advance_sprint` now calls the new
  `_emit_sprint_attention` on both non-auto-advance paths (supervised/directed
  handoff, and idle/no-further-work), so a sprint boundary wakes the manager.
  Autonomous auto-advance does not (it continues itself).

`_emit_attention_needed` now accepts `task_id: str | None` (sprint handoffs
carry no specific task; the digest leads with the handoff instead).

### Documentation

- `docs/MANUAL.md` — 22-section operator manual (mental model, install,
  quickstart, architecture, data model, full CLI reference, roles, workflows,
  multi-model fleet, completion evidence + proof gate, tiered review, meta-agent
  + supervision, autonomy, gates/waivers, cost/time gates, settings reference,
  dashboard + HTTP API, monitoring, event taxonomy, migrations, validation,
  troubleshooting).
- README points to the manual and its stale "next slice" section is corrected.

## Files changed

- `foreman/orchestrator.py` — builtin-block attention emission;
  `_attention_trigger_for_block`; `_emit_sprint_attention`; `_advance_sprint`
  wiring; `_emit_attention_needed` signature.
- `tests/test_orchestrator.py` — 5 new tests (evidence_failed integration,
  trigger-selection unit, supervised/idle sprint_resolved, autonomous negative).
- `tests/test_digest.py` — 1 new test (sprint_resolved / task_id=None digest).
- `docs/MANUAL.md` (new), `README.md`, `CHANGELOG.md`, `docs/STATUS.md`,
  `docs/reviews/review-md-backend-audit.md` (G1 marked resolved).

## Migrations

- none.

## Risks

- Low. The builtin-block emission fires exactly once per blocked builtin outcome
  (the block path then exits via `transition is None`/`continue`), preserving
  the "exactly one `engine.attention_needed` per block" invariant. Sprint
  attention is emitted only on the engine-stops paths.

## Tests

- `tests/test_orchestrator.py::CompletionGuardTests` — merge-guard block emits
  exactly one `evidence_failed` attention event; `_attention_trigger_for_block`
  selects by `proof_status`.
- `tests/test_orchestrator.py::SprintAdvancementTests` — supervised + directed
  idle emit `sprint_resolved`; autonomous auto-advance emits none.
- `tests/test_digest.py` — sprint_resolved digest with no task leads with the
  handoff and omits the task section.
- `./venv/bin/python -m unittest discover -s tests` → **577 passed** (was 571).
- `./venv/bin/python scripts/validate_repo_memory.py` — clean.

## Acceptance criteria satisfied

- Blocking a task still produces exactly one `engine.attention_needed` event.
- A proof-gate-failed guard block produces an `evidence_failed` trigger.
- A sprint resolving while the engine stops produces a `sprint_resolved`
  trigger; autonomous auto-advance produces none.
- A complete operator manual exists and is discoverable from the README.

## Follow-ups

- Deferred (backlog): Tier-3 SSE pub/sub redesign; frontier-`STEER` tool-enabled
  re-review escape hatch.
