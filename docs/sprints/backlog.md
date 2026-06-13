# Backlog

## Review roadmap from `docs/specs/review.md` — COMPLETE

The deep backend review was the forward implementation roadmap. **All phases
(0–7) are now merged to `main`** (top at `35b667c`, 2026-06-13) and the sprints
are archived under `docs/sprints/archive/`. The per-sprint entries below are
retained for traceability; none are pending. The only open item from the
roadmap is the deferred tool-enabled re-review follow-up (see Sprint 51 note).

### Sprint 47 — review Phase 0 correctness

Fix the remaining Phase 0 bugs with regression tests:

- `signal.task_created` must persist `engine.task_created` against the active
  run.
- `foreman waive-merge` must import and exercise `uuid4`.
- dashboard human/stop events must always reference a real run id.
- dashboard Run/Stop process registry must survive request boundaries and
  terminate spawned `foreman run` processes.
- completion evidence should only be built for decision roles and should be
  invalidated when branch head changes.
- dashboard cancellation should clear stale workflow resume state.
- remove the dead `foreman/executor.py` path.

### Sprint 48 — review Phase 1 multi-model fleet

Add per-role `[agent.env]` resolution, runner env plumbing, endpoint session
isolation docs, token-accounting visibility for zero-cost token runs, and the
`developer_worker` example role.

### Sprint 49 — review Phase 2 manager hardening (implemented on `feat/meta-agent-persistence`)

Persist meta-agent sessions and turns, rebuild compact state on every turn,
make the manager contract honest through CLI gaps, and preserve chat history
across dashboard restarts.

Done: migration 11 (`meta_sessions`/`meta_turns`), store-backed `meta_agent`
with crash-safe turn persistence, `build_state_header`/`build_operating_contract`,
`meta_agent_model` setting, paginated `meta/history`, and `foreman task add`
`--description`/`--sprint`/`--depends-on`. Merged to `main` at `62c2e25`;
archived at `archive/sprint-49-meta-agent-persistence.md`.

### Sprint 50 — review Phase 3 executor overrides and escalation ladder (implemented on `feat/executor-overrides-ladder`)

Add task executor overrides, task complexity, role `model_ladder`, deterministic
model resolution, `workflow.model_selected` events, CLI/API override surfaces,
and architect-created complexity persistence.

Done: migration 12, `Task.executor_overrides`/`complexity`, role
`model_ladder`, `resolve_step_model` wired into the workflow loop + native
runner with `workflow.model_selected` events, `signal.task_created` complexity
persistence, `foreman task add --complexity`, `foreman task override`, and
validated `executor_overrides` on `PATCH /api/tasks/{id}`. Merged to `main` at
`2ca7b49`; archived at `archive/sprint-50-executor-overrides-ladder.md`.

### Sprint 51 — review Phases 4 and 5 token economy (implemented on `feat/judge-and-tiered-review`)

Add opt-in LLM-judged criteria evidence, diff payloads for reviewers, cheap
triage review with `escalate`, and the `development_tiered` workflow.

Done: `foreman/judge.py` (heuristic owner + opt-in Anthropic-compatible LLM
judge with head/tail diff truncation), `CompletionEvidence.judged_by`, the
`escalate` outcome, `triage_reviewer`/`frontier_reviewer` roles, the
`{completion_diff}` decision-role prompt payload (`review_diff_max_chars`),
and the `development_tiered` workflow. Merged to `main` at `b53f930`; archived
at `archive/sprint-51-judge-and-tiered-review.md`.

Out of scope (note for later): a tool-enabled "re-review" routing when the
frontier reviewer answers `STEER: need repository context`. Today that carry-
output edge sends the request back to develop; a deeper escape hatch that
re-runs the agentic `code_reviewer` with tools is deferred.

### Sprint 52 — review Phases 6 and 7 supervision and transport cleanup (implemented on `feat/supervision-and-transport`)

Add manager supervision turns for attention-needed events, optimize SSE/watch
polling through SQLite `data_version`, persist retry counts, and complete the
documentation pass for the multi-model/tiered workflow.

Done: `foreman/digest.py`, single `engine.attention_needed` emission per block,
`POST /meta/supervise` (origin=supervision, 409 idempotency, directed
recommend-only), `ForemanStore.data_version()`-gated SSE + watch loops,
persisted `Run.retry_count`, `ProjectSettings` token-economy fields, README +
ADR-0010. This closes the review roadmap. Merged to `main` at `35b667c`;
archived at `archive/sprint-52-supervision-and-transport.md`.

Deferred follow-up: a tool-enabled agentic re-review when the frontier reviewer
answers `STEER: need repository context` (today routes back to develop).

## Tier 3 — Architecture / spec gaps (remaining)

### SSE transport hardening (deferred)

The sprint SSE stream loop polls SQLite directly inside the FastAPI async
generator on a 500 ms interval. This works but is not a final transport design.
Fixing it requires an in-process pub/sub layer (e.g. asyncio queue or
`anyio.Event`) so the generator wakes on a write rather than polling.

- Effort: medium–large
- Urgency: low — current polling is acceptable under normal load
- Prerequisite: decide whether to use an in-process bus or a lightweight broker

## Parking lot

- E2E test coverage for features added in sprints 32–35 (task editing,
  deletion, sprint ordering, date display)
- E2E test coverage for meta agent panel (sprint-40)
- Persist meta agent session history to SQLite (survives server restarts)
- Task `order_index` editing UI within a sprint board (reorder tasks within a
  sprint, similar to sprint ↑/↓ reorder)
- Task priority UI (priority field exists in schema and drawer display but has
  no edit affordance)
- Move task between sprints (no service method or UI; requires task reassignment
  to a different `sprint_id`)
- Codex cost capture — `cost_usd` currently persists as `0.0`; needs Codex
  app-server contract to expose USD pricing
- Run and prompt retention product-level defaults — currently require explicit
  project settings; old runs accumulate if neither is set
