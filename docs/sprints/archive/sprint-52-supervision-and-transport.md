# Sprint 52 — Review Phases 6 & 7 Supervision and Transport Cleanup

- **Branch:** `feat/supervision-and-transport` (top of the stack, on
  `feat/judge-and-tiered-review`)
- **Merged:** 2026-06-13 (fast-forward to `main` at `35b667c`)
- **Status:** done

## Goal

Turn the persisted manager session into a supervision channel for
attention-needed events, optimize SSE/watch polling through SQLite
`data_version`, persist retry counts, and complete the multi-model/tiered
documentation pass. Closes the review roadmap.

## Tasks completed

| # | Task | Deliverable |
|---|------|-------------|
| 1 | Attention digest | `foreman/digest.py` `build_attention_digest` — compact digest (trigger, affected task row, evidence verdict + failure reasons, last run detail, allowed responses; directed mode forbids mutation, supervised lists CLI verbs) |
| 2 | Single attention event | Orchestrator emits exactly one `engine.attention_needed` per block, centralized in `_create_system_run` (plus the `signal.blocker` path); loop limit tagged `loop_limit` |
| 3 | Supervise endpoint | `POST /api/projects/{id}/meta/supervise` — builds the digest, runs one `origin="supervision"` meta turn, streams NDJSON; idempotent on the consumed `event_id` (409 on replay); validates the event is `engine.attention_needed` |
| 4 | Origin plumbing | `process_message` gained `origin` + `consumed_event_id`; turns persist provenance; `ForemanStore.has_consumed_supervision_event` is the dedup guard |
| 5 | data_version gating | `ForemanStore.data_version()` (PRAGMA) gates the SSE stream loop and the `foreman watch` loop so the expensive query only runs after another connection commits; poll interval lowered to 0.25s |
| 6 | retry_count | `_execute_native_runner_step` counts `agent.infra_error` events; `_complete_run` persists the count into `Run.retry_count` |
| 7 | Settings + docs | Token-economy fields in `ProjectSettings` (`meta_agent_model`, `judge_*`, `review_diff_max_chars`); README multi-model/supervision section; ADR-0010 |

## Files changed

`foreman/digest.py` (new), `foreman/orchestrator.py`, `foreman/meta_agent.py`,
`foreman/store.py`, `foreman/dashboard_backend.py`,
`foreman/dashboard_service.py`, `foreman/cli.py`, `foreman/settings.py`,
`tests/test_digest.py` (new, 4), `tests/test_dashboard.py`,
`tests/test_orchestrator.py`, `tests/test_settings.py`, `tests/test_store.py`,
`docs/adr/ADR-0010-tiered-review-and-llm-judged-evidence.md` (new), `README.md`.

## Migrations

- None. `Run.retry_count` already existed; supervision metadata reuses
  `meta_turns.tool_uses_json` / `origin` from migration 11.

## Test results

- `tests.test_digest` (4), `DashboardMetaAgentTests` supervise cases,
  attention/retry_count/data_version/settings tests
- Full suite: 571 tests passed
- `scripts/validate_repo_memory.py`; `git diff --check`

## Notes / risks

- Supervise idempotency is read-then-stream; two near-simultaneous calls for the
  same event could both pass before either persists. Acceptable for
  human/dashboard-paced invocation.
- `data_version` reflects commits by *other* connections; the stream/watch loops
  hold their own read connection and never write, so engine writes are detected.

## Follow-ups

- Deferred (backlog): tool-enabled agentic re-review for a frontier `STEER:
  need repository context`.
