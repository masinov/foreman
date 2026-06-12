# PR Summary: feat/supervision-and-transport

## Summary

Sprint 52 (review Phases 6 and 7). Phase 6 turns the persisted manager session
into a supervision channel: when the engine needs a decision it raises one
`engine.attention_needed` event, and a new endpoint runs a compact supervision
turn from a digest. Phase 7 polishes transport: SSE and `foreman watch` only run
their expensive query when SQLite actually changed, and `Run.retry_count` is
finally written. This completes the review roadmap.

Top of the stacked review branches: `feat/meta-agent-persistence` →
`feat/executor-overrides-ladder` → `feat/judge-and-tiered-review` →
`feat/supervision-and-transport`.

## Scope

Phase 6:
- `foreman/digest.py` `build_attention_digest`
- orchestrator emits exactly one `engine.attention_needed` per block
  (centralized in `_create_system_run`; `signal.blocker` path; `loop_limit`
  trigger)
- `POST /api/projects/{id}/meta/supervise` (origin="supervision", 409 on
  replayed event, directed mode recommend-only)
- `process_message` `origin` / `consumed_event_id`;
  `ForemanStore.has_consumed_supervision_event`

Phase 7:
- `ForemanStore.data_version()`; `data_version`-gated SSE stream and CLI watch
  loops; poll interval 0.25s
- `Run.retry_count` persisted from counted `agent.infra_error` events
- token-economy settings in `ProjectSettings`
- README multi-model/supervision section; ADR-0010

## Files changed

- `foreman/digest.py` (new), `foreman/orchestrator.py`, `foreman/meta_agent.py`,
  `foreman/store.py`, `foreman/dashboard_backend.py`,
  `foreman/dashboard_service.py`, `foreman/cli.py`, `foreman/settings.py`
- `tests/test_digest.py` (new), `tests/test_dashboard.py`,
  `tests/test_orchestrator.py`, `tests/test_settings.py`, `tests/test_store.py`
- `docs/adr/ADR-0010-tiered-review-and-llm-judged-evidence.md` (new), `README.md`,
  `docs/STATUS.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`

## Migrations

- none (`Run.retry_count` column already existed; supervision metadata reuses
  `meta_turns.tool_uses_json` / `origin` from migration 11)

## Risks

- The supervise idempotency check is read-then-stream; two near-simultaneous
  calls for the same event could both pass the check before either persists.
  Acceptable for human/dashboard-paced invocation.
- `data_version` reflects commits by *other* connections; the stream/watch
  loops hold their own read connection, so engine writes are detected. A
  same-process writer would not bump it, but those loops never write.

## Tests

- `tests/test_digest.py` — digest format, directed no-mutation, supervised
  verbs, missing task (4)
- `tests/test_dashboard.py::DashboardMetaAgentTests` — supervise persists an
  `origin="supervision"` turn with the digest + consumed event id; duplicate →
  409; directed forbids mutation in the prompt; non-attention event → 400
- `tests/test_orchestrator.py` — signal.blocker emits exactly one
  `engine.attention_needed`; native runner records `retry_count` from one
  infra-error replay
- `tests/test_settings.py` — token-economy field defaults, parsing, validation
- `tests/test_store.py` — `data_version` changes on another connection's commit
- `./venv/bin/python -m unittest discover -s tests` — full suite (see commit)
- `./venv/bin/python scripts/validate_repo_memory.py`; `git diff --check`

## Acceptance criteria satisfied

Phase 6:
- blocking a task produces exactly one `engine.attention_needed` event
- `meta/supervise` with a fake Claude subprocess: digest contains the blocked
  reason; turn persisted with `origin="supervision"`; duplicate call → 409
- a `directed` project's supervise prompt contains the no-mutation instruction

Phase 7:
- `data_version()` returns `PRAGMA data_version` and changes when another
  connection commits; SSE and watch loops gate on it
- `Run.retry_count` is written (counted from `agent.infra_error`)
- README, ADR-0010, and CHANGELOG updated

## Follow-ups

- Merge the stacked review branches (Phases 2 → 7) to `main` and archive the
  sprints.
- Optional: tool-enabled re-review routing for a frontier `STEER` (backlog).
